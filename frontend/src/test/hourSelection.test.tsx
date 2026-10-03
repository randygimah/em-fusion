import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import {
  DEFAULT_POLL_INTERVAL_MS,
  OPERATIONAL_PICTURE_PATH,
  SCENARIO_RUNS_PATH,
  SELECTABLE_HOURS_PATH,
} from "../lib/api";
import operationalPictureMock from "../mocks/operationalPictureMock";
import type { OperationalPicture, SelectableHour } from "../types/operationalPicture";

// spec: op-009 — the hour selector on the Operational Picture.
//
// The screen could only ever be asked for the newest hour. Four hundred hours
// are stored, every one examined, and two hundred and forty hold something an
// analyst would be shown; this is the control that reaches them.
//
// Three of the assertions here are about what must NOT happen, and each of the
// three has a named precedent in this project. The control must not name an
// hour's scenario type, which put `gnss-degradation` in this screen's heading
// for a year and survived because the same words are legitimate one screen
// over. The list must not come from the harness's runs endpoint, which carries
// that string on purpose. And a pinned hour must not look like a live one,
// which is the same class of defect as a health signal reporting healthy
// through an outage.

// The five arms, scanned for across the whole rendered screen. A check on the
// one field somebody thought of is the mistake api-012 recorded.
const ARMS = [
  "normal-baseline",
  "gnss-degradation",
  "aircraft-coverage-gap",
  "rf-sensor-fault",
  "ambiguous-mixed-evidence",
];

const HOURS: SelectableHour[] = [
  {
    runId: 420,
    observedFrom: "2022-06-27T12:00:00Z",
    observedTo: "2022-06-27T12:15:00Z",
    examined: true,
  },
  {
    runId: 207,
    observedFrom: "2022-06-27T09:30:00Z",
    observedTo: "2022-06-27T09:45:00Z",
    examined: true,
  },
  {
    runId: 108,
    observedFrom: null,
    observedTo: null,
    examined: false,
  },
];

const picture = (runId: number): OperationalPicture => ({
  ...operationalPictureMock,
  scenario: { id: String(runId), name: `Run ${runId}`, dataMode: "mixed", health: "unknown" },
  hypotheses: [],
  rfSensors: [],
  timelineEvents: [],
  detectionSummary: null,
  aircraftTracks: [],
});

const ok = (payload: unknown) => ({ ok: true, status: 200, json: async () => payload }) as Response;

let fetchMock: ReturnType<typeof vi.fn>;

const route = (input: RequestInfo | URL): Response => {
  const url = String(input);
  if (url.includes(SELECTABLE_HOURS_PATH)) return ok(HOURS);
  const match = /[?&]run=(\d+)/.exec(url);
  return ok(picture(match ? Number(match[1]) : 420));
};

const pictureCalls = () =>
  fetchMock.mock.calls
    .map((call) => String(call[0]))
    .filter((url) => url.includes(OPERATIONAL_PICTURE_PATH) && !url.includes(SELECTABLE_HOURS_PATH));

// `@testing-library/user-event` is not a dependency here and a select is not
// worth adding one for: every other suite in this project drives its controls
// with fireEvent, and a change event is what a select emits.
const selectHour = (runId: string) =>
  fireEvent.change(screen.getByRole("combobox", { name: /hour/i }), { target: { value: runId } });

beforeEach(() => {
  fetchMock = vi.fn((input: RequestInfo | URL) => Promise.resolve(route(input)));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("the hour selector", () => {
  it("fetches the index of selectable hours", async () => {
    render(<App />);

    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => String(call[0]).includes(SELECTABLE_HOURS_PATH))).toBe(
        true,
      ),
    );
  });

  it("offers every hour the index served", async () => {
    render(<App />);

    for (const hour of HOURS) {
      expect(await screen.findByRole("option", { name: new RegExp(String(hour.runId)) })).toBeInTheDocument();
    }
  });

  it("labels an hour by its replayed window as well as its number", async () => {
    // The run number is what every measurement log cites and is unreadable on
    // its own; the window is the hour an analyst means.
    render(<App />);

    const option = await screen.findByRole("option", { name: /420/ });

    expect(option).toHaveAccessibleName(expect.stringMatching(/2022/));
  });

  it("labels an hour that records no window by its number alone", async () => {
    // spec: api-013 amendment (a) — a replay run records no simulated window,
    // and the alternative is borrowing the generator's wall clock.
    render(<App />);

    const option = await screen.findByRole("option", { name: /108/ });

    expect(option).toHaveAccessibleName(expect.not.stringMatching(/2022/));
  });

  it("lists an unexamined hour rather than hiding or disabling it", async () => {
    // An unexamined hour is a legitimate thing to look at, and hiding it would
    // make a batch whose scoring was refused invisible — the one condition
    // anom-016 reports only through the summary's sentence.
    render(<App />);

    const option = (await screen.findByRole("option", { name: /108/ })) as HTMLOptionElement;

    expect(option.disabled).toBe(false);
  });

  it("states that the store holds no hour rather than rendering a blank control", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) =>
      Promise.resolve(String(input).includes(SELECTABLE_HOURS_PATH) ? ok([]) : route(input)),
    );
    render(<App />);

    expect(await screen.findByText(/no completed hour/i)).toBeInTheDocument();
  });
});

describe("following the newest hour, and pinning one", () => {
  it("follows the newest hour before anything is selected", async () => {
    render(<App />);

    await waitFor(() => expect(pictureCalls().length).toBeGreaterThan(0));
    expect(pictureCalls()[0]).not.toContain("run=");
    expect(await screen.findByText(/following the newest/i)).toBeInTheDocument();
  });

  it("asks for the hour that was selected", async () => {
    render(<App />);
    await screen.findByRole("option", { name: /207/ });

    selectHour("207");

    await waitFor(() => expect(pictureCalls().at(-1)).toContain("run=207"));
  });

  it("says it is pinned rather than live once an hour is selected", async () => {
    // The named failure case: an analyst pins an hour, a batch lands, and the
    // screen goes on showing the pinned hour while looking identical to a live
    // one. Stale data in the costume of current data.
    render(<App />);
    await screen.findByRole("option", { name: /207/ });

    selectHour("207");

    expect(await screen.findByText(/pinned/i)).toBeInTheDocument();
    expect(screen.queryByText(/following the newest/i)).not.toBeInTheDocument();
  });

  it("offers a way back to following the newest", async () => {
    render(<App />);
    await screen.findByRole("option", { name: /207/ });
    selectHour("207");
    await screen.findByText(/pinned/i);

    fireEvent.click(screen.getByRole("button", { name: /newest/i }));

    expect(await screen.findByText(/following the newest/i)).toBeInTheDocument();
    await waitFor(() => expect(pictureCalls().at(-1)).not.toContain("run="));
  });

  it("keeps polling the pinned hour rather than reverting to the newest", async () => {
    // Keeps polling, because re-examining a run restamps it and 380 runs'
    // findings changed in six minutes on 3 October. Polls the PINNED hour,
    // because a poll that kept asking for the newest would revert the screen
    // under the analyst on the next tick.
    render(<App />);
    await screen.findByRole("option", { name: /207/ });
    selectHour("207");
    await waitFor(() => expect(pictureCalls().at(-1)).toContain("run=207"));

    vi.useFakeTimers({ shouldAdvanceTime: true });
    const before = pictureCalls().length;
    await vi.advanceTimersByTimeAsync(DEFAULT_POLL_INTERVAL_MS);

    await waitFor(() => expect(pictureCalls().length).toBeGreaterThan(before));
    expect(pictureCalls().at(-1)).toContain("run=207");
  });
});

describe("the answer key reaches no part of this screen", () => {
  it("never renders a scenario type, from any source", async () => {
    // spec: api-009 — the same string is correct on Scenario Control and
    // disqualifying here, which is why a repo-wide search for it finds a
    // justified use and stops.
    render(<App />);
    await screen.findByRole("option", { name: /420/ });

    for (const arm of ARMS) {
      expect(screen.queryByText(new RegExp(arm, "i"))).not.toBeInTheDocument();
    }
  });

  it("takes the hours from the index and never from the harness listing", async () => {
    render(<App />);
    await screen.findByRole("option", { name: /420/ });

    expect(fetchMock.mock.calls.map((call) => String(call[0])).join(" ")).not.toContain(
      SCENARIO_RUNS_PATH,
    );
  });
});

// --------------------------------------------------------- structural

// The picture side of the app, named rather than globbed, because App.tsx
// legitimately imports the scenario feed for the other route — so a check over
// every module would either fail on the seam or have to exempt it, and an
// exemption is where this rule would quietly stop applying.
const PICTURE_MODULES = [
  "../screens/operationalPicture.tsx",
  "../hooks/useOperationalPicture.ts",
  "../hooks/useSelectableHours.ts",
];

const sources = import.meta.glob("../**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

// Comments first, then string literals, so a rule *described* is not mistaken
// for a rule *broken* — transport.test.ts's own scrubber and its reasoning.
const scrub = (source: string): string =>
  source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/\/\/[^\n]*/g, " ")
    .replace(/`(?:\\.|[^`\\])*`/g, '""')
    .replace(/"(?:\\.|[^"\\])*"/g, '""')
    .replace(/'(?:\\.|[^'\\])*'/g, '""');

describe("the picture does not reach the harness's list", () => {
  it("checks the modules it claims to check", () => {
    // An empty list makes every assertion below a comparison of nothing, which
    // is how a structural test most often fails: silently, and green.
    for (const path of PICTURE_MODULES) {
      expect(Object.keys(sources)).toContain(path);
    }
  });

  it.each(PICTURE_MODULES)("%s names neither the harness fetcher nor its contract", (path) => {
    // spec: op-009, api-009 — the list of selectable hours comes from the
    // picture's own index. The harness listing carries the scenario type for
    // Scenario Control's legitimate use, and reusing it here would put the
    // answer key in the analyst's browser with only a convention keeping it
    // off the screen.
    const source = scrub(sources[path]);

    expect(source).not.toContain("fetchScenarioRuns");
    expect(source).not.toContain("scenarioControl");
    expect(source).not.toContain("useScenarioControl");
  });

  it("finds the forbidden name when it is really there", () => {
    // The interlock: fired at the scenario route's own hook, which imports the
    // harness fetcher on purpose. A scan that cannot find a real violation is
    // not a scan.
    expect(scrub(sources["../hooks/useScenarioControl.ts"])).toContain("fetchScenarioRuns");
  });
});
