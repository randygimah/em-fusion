import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import {
  DEFAULT_POLL_INTERVAL_MS,
  OPERATIONAL_PICTURE_PATH,
  SYSTEM_HEALTH_INTERVAL_MS,
  SYSTEM_HEALTH_PATH,
} from "../lib/api";
import { EmSystemStatus } from "../components/em/EmSystemStatus";
import type { Service } from "../hooks/useSystemHealth";
import operationalPictureMock from "../mocks/operationalPictureMock";
import { SCREENS } from "../routes";

// spec: nav-002 — the system-status strip in the nav footer.
//
// The item named its input as a health value on the picture payload. That value
// was hard-coded to `unknown` in the builder with a comment saying no health
// monitoring existed, and it was a property of one run while this strip is in
// the rail and therefore on all three screens. api-014 removes it.
//
// What exists instead, and did not when the item was written, is the service's
// own health route: it reports whether the database is at the revision the code
// expects, in three states, and the third is the design — drifted REFUSES with a
// 503, unreachable answers 200 saying it could not tell, because an outage is
// not a misconfiguration.
//
// The two rows are that same split one layer further out, and the sharpest test
// here is the trap: a 503 means the request ARRIVED and the backend could not
// vouch for itself, so connectivity is up and the service row carries the
// refusal. Read as a failed request it would report a misconfigured deployment
// as a lost connection — which is the conflation the schema-drift item ended.

const AT_HEAD = { status: "healthy", schema: "at-head", expected: "0009", found: "0009", detail: "ok" };
const DRIFTED = {
  status: "unhealthy",
  schema: "drifted",
  expected: "0009",
  found: "0008",
  detail: "this database is at 0008 and this code expects 0009",
};
const CANNOT_TELL = {
  status: "healthy",
  schema: "unknown",
  expected: "0009",
  found: null,
  detail: "OperationalError",
};

const ok = (payload: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => payload }) as Response;

let fetchMock: ReturnType<typeof vi.fn>;
let health: () => Response;

const route = (input: RequestInfo | URL): Response => {
  const url = String(input);
  if (url.includes(SYSTEM_HEALTH_PATH)) return health();
  if (url.includes("/hours")) return ok([]);
  if (url.includes("/scenario/runs")) return ok([]);
  return ok({
    ...operationalPictureMock,
    scenario: { id: "1", name: "Run 1", dataMode: "mixed" },
    hypotheses: [],
    rfSensors: [],
    timelineEvents: [],
    detectionSummary: null,
    aircraftTracks: [],
  });
};

beforeEach(() => {
  window.location.hash = "";
  window.localStorage.clear();
  health = () => ok(AT_HEAD);
  fetchMock = vi.fn((input: RequestInfo | URL) => Promise.resolve(route(input)));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.location.hash = "";
  window.localStorage.clear();
});

const rail = () => screen.getByRole("navigation", { name: /screens/i });
// Scoped to the rail rather than to a container element of the strip's own: the
// strip carries no container role, because each row is a `status` with its own
// accessible name and an invented role on top of that adds nothing. Scanning
// the whole rail is also the stronger claim for the no-percentage test — no
// percentage anywhere in the rail, not merely none inside one box.
const strip = rail;
const row = (name: RegExp) => within(rail()).getByRole("status", { name });

describe("the strip, and where it reads from", () => {
  it("asks the service's own health route", async () => {
    render(<App />);

    await waitFor(() =>
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes(SYSTEM_HEALTH_PATH))).toBe(true),
    );
  });

  it.each(SCREENS.map((s) => [s.label, s.hash] as const))("is on the %s screen", async (_l, hash) => {
    window.location.hash = hash;
    render(<App />);

    expect(await within(rail()).findByText(/system status/i)).toBeInTheDocument();
    expect(row(/connectivity/i)).toBeInTheDocument();
    expect(row(/service/i)).toBeInTheDocument();
  });

  it("does not read the picture payload", () => {
    // The payload field it was specified against is gone (api-014), and reading
    // the picture here would need its poll on every screen.
    //
    // The exact route, not `includes`. This filter was written when the
    // picture's path belonged to one endpoint, and excluded `/hours` by name
    // when op-009 added a second; op-010's `/evidence` then made it count two
    // calls again. Spelling the path as a literal here is also why a search for
    // the constant missed this site — the fourth of four.
    render(<App />);

    const pictureCalls = fetchMock.mock.calls
      .map((c) => String(c[0]))
      .filter((u) => u.split("?")[0] === OPERATIONAL_PICTURE_PATH);
    expect(pictureCalls.length).toBeLessThanOrEqual(1);
  });

  it("does not become a fourth nav entry", () => {
    // spec: nav-001, FR-701, FR-702 — a strip, not a screen and not an entry.
    render(<App />);

    expect(within(rail()).getAllByRole("link")).toHaveLength(SCREENS.length);
  });
});

describe("the two rows, and the three states behind them", () => {
  it("reports both good when the service is at the expected revision", async () => {
    render(<App />);

    expect(await within(strip()).findByText(/connected/i)).toBeInTheDocument();
    expect(within(strip()).getByText(/healthy/i)).toBeInTheDocument();
  });

  it("reports the service refusing while connectivity stays up on a 503", async () => {
    // THE TRAP. A 503 means the request arrived and the backend could not vouch
    // for itself. Read as a failed request, a misconfigured deployment reports
    // as a lost connection — the exact conflation ops-005 removed, and the
    // state that cost a day of a screen returning 500 while the container said
    // it was healthy.
    health = () => ok(DRIFTED, 503);
    render(<App />);

    expect(await within(strip()).findByText(/schema behind/i)).toBeInTheDocument();
    expect(row(/connectivity/i)).toHaveAccessibleName(/connected/i);
  });

  it("reports that it could not tell when the backend cannot reach its database", async () => {
    // Distinct from the refusal above: an outage is not a misconfiguration, and
    // collapsing the two makes a deployment that has not finished look like one
    // that has broken.
    health = () => ok(CANNOT_TELL);
    render(<App />);

    expect(await within(strip()).findByText(/database unreachable/i)).toBeInTheDocument();
    expect(within(strip()).queryByText(/schema behind/i)).not.toBeInTheDocument();
  });

  it("reports connectivity down when the request never arrives", async () => {
    health = () => {
      throw new Error("network down");
    };
    render(<App />);

    expect(await within(strip()).findByText(/no connection/i)).toBeInTheDocument();
  });

  it("keeps the two refusals distinguishable", () => {
    // Asserted as a PAIR rather than per state, because the failure is that the
    // two render identically — and each of the two tests above would still pass
    // if they did, since each only checks that its own wording appears.
    //
    // Driven at the component rather than through App: two renders of the whole
    // app in one test leaves two strips in the document and the comparison then
    // reads whichever the query returned first, which is the unordered-result
    // mistake this repository has recorded three times.
    const render_ = (service: Service) =>
      render(<EmSystemStatus connectivity="up" service={service} />).container.textContent;

    expect(render_("refusing")).not.toEqual(render_("cannot-tell"));
  });

  it("treats a body missing the keys it reads as unreachable, not as a verdict", async () => {
    // The one silent failure available here: the health body is a plain dict
    // with no model to parity-check against, so a renamed key would make the
    // strip read `undefined`, map it to a verdict, and report a plausible
    // steady state forever. It degrades to a visible failure instead.
    health = () => ok({ state: "healthy", schemaState: "at-head" });
    render(<App />);

    expect(await within(strip()).findByText(/no connection|unreachable/i)).toBeInTheDocument();
    expect(within(strip()).queryByText(/^healthy$/i)).not.toBeInTheDocument();
  });
});

describe("what the strip may not do", () => {
  it("renders no percentage anywhere", async () => {
    // The item's named failure case — and the design reference itself renders
    // "99.9% UPTIME" in this panel, so it is not hypothetical.
    render(<App />);
    await within(strip()).findByText(/connected/i);

    expect(strip().textContent ?? "").not.toMatch(/%/);
  });

  it("renders no decimal or numeric state", async () => {
    render(<App />);
    await within(strip()).findByText(/connected/i);

    expect(strip().textContent ?? "").not.toMatch(/\d+\.\d+/);
  });

  it("keeps both rows when the rail collapses", async () => {
    // nav-003's rule: collapsing hides labels, never entries. At 56px the
    // labelled rows do not fit, so each becomes a dot carrying its row name and
    // state as its accessible name — and neither row is dropped.
    render(<App />);
    await within(strip()).findByText(/connected/i);

    fireEvent.click(screen.getByRole("button", { name: /collapse navigation/i }));

    expect(row(/connectivity/i)).toBeInTheDocument();
    expect(row(/service/i)).toBeInTheDocument();
  });

  it("polls on its own interval, slower than the picture's", () => {
    // What it reports changes only when somebody runs a migration or the
    // database goes away, and ops-005 reads the database's revision on every
    // single probe by design — so the picture's cadence would be a database
    // round trip every five seconds per open screen.
    expect(SYSTEM_HEALTH_INTERVAL_MS).toBeGreaterThan(DEFAULT_POLL_INTERVAL_MS);
  });

  it("asks again after its own interval", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<App />);
    const healthCalls = () =>
      fetchMock.mock.calls.filter((c) => String(c[0]).includes(SYSTEM_HEALTH_PATH)).length;

    await waitFor(() => expect(healthCalls()).toBe(1));
    await vi.advanceTimersByTimeAsync(SYSTEM_HEALTH_INTERVAL_MS);

    await waitFor(() => expect(healthCalls()).toBe(2));
  });
});
