import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import {
  DEFAULT_POLL_INTERVAL_MS,
  EVIDENCE_PATH,
  OPERATIONAL_PICTURE_PATH,
  SCENARIO_RUNS_PATH,
  SELECTABLE_HOURS_PATH,
} from "../lib/api";
import operationalPicture from "../mocks/operationalPictureMock";
import type { EvidenceAccount } from "../types/evidence";
import type { OperationalPicture } from "../types/operationalPicture";

// spec: op-010, api-015 — fetching the account for the hour on screen.
//
// Two decisions are asserted here and both are about which hour an answer
// belongs to.
//
// **Not polled.** The account changes only when a detection pass runs, which
// is when a batch completes, so a five-second poll would re-fetch a large
// payload to learn nothing — `op-009`'s argument for the hour index.
//
// **A failure does not keep what is on screen.** `api-003`'s keep-what-is-there
// rule governs polling ONE thing, and this fetch is keyed on the hour: a
// failure after a success can only follow a change of hour, so keeping the old
// answer would show one hour's evidence under another hour's conclusion, which
// is the conflation the whole item exists to remove.

const picture: OperationalPicture = {
  ...operationalPicture,
  scenario: { id: "420", name: "run 420", dataMode: "replayed" },
  hypotheses: [],
  rfSensors: [],
  timelineEvents: [],
  detectionSummary: null,
};

const served: EvidenceAccount = {
  runId: 420,
  explained: [],
  unexplained: [
    {
      ruleId: "FUSION-SPATIAL",
      findingType: "possible_interference_zone",
      subject: "RF-04",
      observedFrom: "2022-06-27T12:31:22+00:00",
      observedTo: "2022-06-27T12:36:52+00:00",
      reason: "not-bundled",
    },
  ],
  unclaimed: [],
};

const ok = (payload: unknown) => ({ ok: true, status: 200, json: async () => payload }) as Response;
const failure = (status: number) =>
  ({ ok: false, status, json: async () => ({}) }) as Response;

let fetchMock: ReturnType<typeof vi.fn>;

const route = (url: unknown) => String(url).split("?")[0];

// Exact path, not `includes`. The prefix form was equivalent only while one
// endpoint existed; op-009 added `/hours` and this item adds `/evidence`, both
// of which carry the picture's path as a prefix. Comparing the route rather
// than searching the string is what stops a fourth sub-path breaking these
// counts a third time.
const evidenceCalls = () =>
  fetchMock.mock.calls.map((call) => String(call[0])).filter((url) => route(url) === EVIDENCE_PATH);

const answer = (url: unknown) => {
  const path = route(url);
  if (path === EVIDENCE_PATH) return ok(served);
  if (path === SELECTABLE_HOURS_PATH) return ok([{ runId: 420, observedFrom: null, observedTo: null, examined: true }]);
  if (path === OPERATIONAL_PICTURE_PATH) return ok(picture);
  // The other screen's own endpoint, because one of these tests navigates
  // there. Answered by route rather than by fallthrough — a fallthrough is how
  // this helper would serve a health body to a screen expecting a run list.
  if (path === SCENARIO_RUNS_PATH) return ok([]);
  return ok({ status: "ok", schema: "at-head" });
};

const panel = () => screen.getByRole("region", { name: "Evidence" });

// `@testing-library/user-event` is not a dependency here, and every other
// suite in this project drives its controls with fireEvent.
const selectHour = (runId: string) =>
  fireEvent.change(screen.getByRole("combobox", { name: /hour/i }), { target: { value: runId } });

beforeEach(() => {
  fetchMock = vi.fn((url: unknown) => Promise.resolve(answer(url)));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("fetching the evidence account", () => {
  it("asks the backend on the contract's path", async () => {
    render(<App />);

    await waitFor(() => expect(evidenceCalls().length).toBeGreaterThan(0));
    expect(route(evidenceCalls()[0])).toBe(EVIDENCE_PATH);
  });

  it("asks for no particular hour while following the newest", async () => {
    // spec: op-010, api-015 — the endpoint with no run parameter serves the
    // same hour the picture does, so the two cannot disagree about which is
    // current
    render(<App />);

    await waitFor(() => expect(evidenceCalls().length).toBeGreaterThan(0));
    expect(evidenceCalls()[0]).not.toContain("run=");
  });

  it("renders what the backend served", async () => {
    render(<App />);

    await waitFor(() =>
      expect(panel()).toHaveTextContent(/Possible interference across several receivers/),
    );
  });

  it("does not poll", async () => {
    // spec: op-010, op-009 — the account changes only when a pass runs. Fake
    // timers are installed BEFORE the render: installed after, they do not
    // adopt an interval already scheduled on real timers, and the test then
    // compares a count with itself.
    vi.useFakeTimers();
    render(<App />);

    await vi.advanceTimersByTimeAsync(DEFAULT_POLL_INTERVAL_MS * 4);

    expect(evidenceCalls()).toHaveLength(1);
  });

  it("asks for the pinned hour's evidence when an hour is pinned", async () => {
    // spec: op-010, op-009 — pinning an hour has to move the panel with it,
    // or the evidence on screen belongs to a different hour than the
    // conclusion above it
    render(<App />);
    await waitFor(() => expect(evidenceCalls().length).toBeGreaterThan(0));

    selectHour("420");

    await waitFor(() => expect(evidenceCalls().some((url) => url.includes("run=420"))).toBe(true));
  });

  it("says it could not load the evidence when the fetch fails", async () => {
    // spec: op-010 — and never the sentence for an unexamined hour, which
    // would report a transport failure as a fact about the store
    fetchMock.mockImplementation((url: unknown) =>
      Promise.resolve(route(url) === EVIDENCE_PATH ? failure(500) : answer(url)),
    );
    render(<App />);

    await waitFor(() => expect(panel()).toHaveTextContent(/could not (be )?load/i));
    expect(panel()).not.toHaveTextContent(/not been examined/i);
  });

  it("does not leave the previous hour's evidence on screen when a later fetch fails", async () => {
    // spec: op-010 — the amendment, and the reason `api-003`'s rule does not
    // transfer: what is on screen belongs to a different hour
    render(<App />);
    await waitFor(() =>
      expect(panel()).toHaveTextContent(/Possible interference across several receivers/),
    );

    fetchMock.mockImplementation((url: unknown) =>
      Promise.resolve(route(url) === EVIDENCE_PATH ? failure(500) : answer(url)),
    );
    selectHour("420");

    await waitFor(() =>
      expect(within(panel()).queryByText(/Possible interference across several receivers/)).toBeNull(),
    );
  });

  it("renders the panel on the picture screen and nowhere else", async () => {
    // spec: op-010, nav-001 — the evidence belongs to the picture's hour, and
    // the other two screens have no hour
    render(<App />);
    await waitFor(() => expect(evidenceCalls().length).toBeGreaterThan(0));

    window.location.hash = "#/scenario-control";
    window.dispatchEvent(new HashChangeEvent("hashchange"));

    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Evidence" })).toBeNull(),
    );
  });
});
