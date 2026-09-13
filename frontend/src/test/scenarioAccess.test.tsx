import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import {
  DEFAULT_POLL_INTERVAL_MS,
  SCENARIO_RUNS_PATH,
  SCENARIO_START_PATH,
  fetchScenarioRuns,
  startScenarioBatch,
} from "../lib/api";
import scenarioControlMock from "../mocks/scenarioControlMock";
import { DEFAULT_CONFIGURATION } from "../types/scenarioControl";

// spec: api-010 — the Scenario Control screen stops reading a fixture.

const SCENARIO_HASH = "#/scenario-control";

const RUNS = [
  {
    id: 48,
    scenarioType: "gnss-degradation",
    seed: 811000111,
    startedAt: "2026-09-13T09:47:03",
    completedAt: null,
    parameters: { ...scenarioControlMock.runs[0].parameters },
  },
  {
    id: 47,
    scenarioType: "normal-baseline",
    seed: 822000222,
    startedAt: "2026-09-13T09:45:58",
    completedAt: "2026-09-13T09:46:08",
    parameters: { ...scenarioControlMock.runs[0].parameters },
  },
];

const ok = (body: unknown): Response =>
  ({ ok: true, status: 200, json: async () => body }) as Response;

const table = () => within(screen.getByRole("table", { name: /recent runs/i }));

beforeEach(() => {
  window.location.hash = SCENARIO_HASH;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.location.hash = "";
});

// ------------------------------------------------------------- the transport

describe("the scenario transport", () => {
  it("asks the versioned paths the backend owns", async () => {
    // spec: api-010, api-006 — the backend owns /api/v1, and nothing here
    // rewrites it; the same relative-path reasoning as api-003
    const fetchMock = vi.fn().mockResolvedValue(ok(RUNS));
    vi.stubGlobal("fetch", fetchMock);

    await fetchScenarioRuns();

    expect(SCENARIO_RUNS_PATH).toBe("/api/v1/scenario/runs");
    expect(SCENARIO_START_PATH).toBe("/api/v1/scenario/start");
    expect(fetchMock.mock.calls[0][0]).toBe(SCENARIO_RUNS_PATH);
  });

  it("returns the runs the backend listed", async () => {
    // spec: api-010
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(RUNS)));

    expect(await fetchScenarioRuns()).toEqual(RUNS);
  });

  it("throws when the runs cannot be read", async () => {
    // spec: api-010, api-003 — thrown rather than returned as a value, so
    // every caller has to handle a failure rather than forget to check a flag
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 } as Response));

    await expect(fetchScenarioRuns()).rejects.toThrow(/503/);
  });

  it("posts the configuration and returns what was accepted", async () => {
    // spec: api-010, api-006 — the seed the server used comes back, including
    // one it drew, because a batch whose seed nobody was told cannot be repeated
    const accepted = { baseSeed: 20220627, runs: 20, seeds: [1, 2, 3] };
    const fetchMock = vi.fn().mockResolvedValue(ok(accepted));
    vi.stubGlobal("fetch", fetchMock);

    const result = await startScenarioBatch(DEFAULT_CONFIGURATION);

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe(SCENARIO_START_PATH);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual(DEFAULT_CONFIGURATION);
    expect(result).toEqual(accepted);
  });

  it("throws when a batch is refused", async () => {
    // spec: api-010, api-006 — the backend refuses an unknown type, a batch
    // outside the bounds, and an incident that begins after its run ends
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422 } as Response));

    await expect(startScenarioBatch(DEFAULT_CONFIGURATION)).rejects.toThrow(/422/);
  });
});

// ------------------------------------------------------------- on the screen

describe("the Scenario Control screen against the backend", () => {
  it("lists the runs the database holds", async () => {
    // spec: api-010 — the rows are the system's own, at last
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(RUNS)));

    render(<App />);

    expect(await table().findByText("811000111")).toBeInTheDocument();
    expect(table().getByText("822000222")).toBeInTheDocument();
    // And the fixture's own rows are gone. Without this the test passes on a
    // screen still rendering the mock, which is what it exists to rule out --
    // it did, until the seeds above were changed to ones the mock never used.
    for (const run of scenarioControlMock.runs) {
      expect(screen.queryByText(String(run.seed))).not.toBeInTheDocument();
    }
  });

  it("shows no rows at all before the first answer arrives", async () => {
    // spec: api-010 (third decision) — the whole point of the item. Rows
    // lifted from a real batch are indistinguishable from the database's own,
    // so the fallback is emptiness rather than fiction.
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    render(<App />);

    const fixtureSeed = String(scenarioControlMock.runs[0].seed);
    expect(screen.queryByText(fixtureSeed)).not.toBeInTheDocument();
    // The exact claim, not just "no runs": the screen has to say the list has
    // not been read, which is a statement about the system rather than about
    // the database. "No runs recorded yet" would assert the second.
    expect(await screen.findByText(/the run list has not been read/i)).toBeInTheDocument();
  });

  it("no longer says the listed runs are a fixture", async () => {
    // spec: api-010 — nav-001 put that sentence on screen because it was true.
    // Leaving it there once the rows are real would be the same failure in the
    // other direction: a true system described as an example one.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(RUNS)));

    render(<App />);
    await table().findByText("811000111");

    expect(screen.queryByText(/fixture/i)).not.toBeInTheDocument();
  });

  it("keeps the runs on screen when a later poll fails", async () => {
    // spec: api-010 (fifth failure case), api-003 — stale truth beats fresh
    // nothing, and only the indicator changes
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok(RUNS))
      .mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetchMock);
    vi.useFakeTimers();

    render(<App />);
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(DEFAULT_POLL_INTERVAL_MS * 2);

    expect(table().getByText("811000111")).toBeInTheDocument();
  });

  it("stops polling for runs when the analyst leaves the screen", async () => {
    // spec: api-010 (sixth decision), nav-001 — a second five-second poll
    // against an endpoint nobody is watching would undo what nav-001 fixed
    const fetchMock = vi.fn().mockResolvedValue(ok(RUNS));
    vi.stubGlobal("fetch", fetchMock);
    vi.useFakeTimers();

    render(<App />);
    await vi.advanceTimersByTimeAsync(DEFAULT_POLL_INTERVAL_MS * 2);
    const polled = fetchMock.mock.calls.length;

    fireEvent.click(screen.getByRole("link", { name: /hypotheses/i }));
    await vi.advanceTimersByTimeAsync(DEFAULT_POLL_INTERVAL_MS * 3);

    expect(polled).toBeGreaterThan(0);
    expect(fetchMock.mock.calls).toHaveLength(polled);
  });

  it("starts a batch and names the seed the server used", async () => {
    // spec: api-010 (fourth decision) — a 202 that changes nothing on screen
    // reads as a dead button, and the seed is what makes the batch repeatable
    const fetchMock = vi.fn().mockImplementation((path: string) =>
      path === SCENARIO_START_PATH
        ? Promise.resolve(ok({ baseSeed: 1735359291, runs: 20, seeds: [1] }))
        : Promise.resolve(ok(RUNS)),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /start batch/i }));

    expect(await screen.findByText(/1735359291/)).toBeInTheDocument();
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([path]) => path === SCENARIO_START_PATH),
      ).toBe(true),
    );
  });

  it("leaves reset and replay disabled, because neither has an endpoint", async () => {
    // spec: api-010 (fifth decision), api-006 — reset was deferred, and a
    // single-run replay is not a request this API can make: a batch is between
    // 20 and 30 runs (scn-003)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(RUNS)));

    render(<App />);
    await table().findByText("811000111");

    expect(screen.getByRole("button", { name: /^reset$/i })).toBeDisabled();
    for (const replay of table().getAllByRole("button", { name: /replay/i })) {
      expect(replay).toBeDisabled();
    }
  });
});

// --------------------------------------------------------- the seam holds

describe("where the screen's data comes from", () => {
  const modules = import.meta.glob("../**/*.{ts,tsx}", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  // Comments stripped, string literals kept. transport.test.ts scrubs both,
  // and must: it looks for `fetch(`, which a comment can name innocently. This
  // check looks for an *import*, and an import path IS a string literal — so
  // scrubbing strings here would make it match nothing at all, green forever.
  // The trap is the same one either way: a rule described must not read as a
  // rule broken. `scenarioLibrary.ts` explains in prose where it came from,
  // and that sentence is why this scrubber exists.
  const stripComments = (source: string): string =>
    source.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");

  const appModules = Object.entries(modules).filter(
    ([path]) =>
      !path.startsWith("../test/") &&
      !path.startsWith("./") &&
      !path.startsWith("../mocks/"),
  );

  it("checks the files it claims to check", () => {
    // An empty list would make the assertion below pass silently, which is how
    // a structural test most often fails (transport.test.ts, same trap)
    expect(appModules.map(([path]) => path)).toContain("../App.tsx");
  });

  it("still catches a real import", () => {
    // Without this, the scrubber above proves only that nothing is checked.
    const real = stripComments('import mock from "../mocks/scenarioControlMock";');
    const described = stripComments("// never import mocks/scenarioControlMock here");

    expect(real.includes("mocks/scenarioControlMock")).toBe(true);
    expect(described.includes("mocks/scenarioControlMock")).toBe(false);
  });

  it("imports the scenario fixture nowhere in the app", () => {
    // spec: api-010 (second decision) — the library moved out of the mock, so
    // nothing outside the tests needs it any more
    const offenders = appModules
      .filter(([, source]) => stripComments(source).includes("mocks/scenarioControlMock"))
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });
});
