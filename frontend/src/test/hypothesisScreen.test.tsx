import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { affectedAreaBounds, matchZone } from "../lib/affectedArea";
import { fetchHypotheses, fetchHypothesis, HYPOTHESES_PATH, HypothesisNotFoundError } from "../lib/api";
import operationalPictureMock from "../mocks/operationalPictureMock";
import HypothesesScreen from "../screens/hypotheses";
import screenSource from "../screens/hypotheses.tsx?raw";
import type { HypothesisDetail, HypothesisList, HypothesisSummary, VerdictRequest } from "../types/hypotheses";
import type { InterferenceZone, OperationalPicture, RFSensor } from "../types/operationalPicture";

// spec: hyp-001 (amended 2026-10-11) — the Hypotheses screen: the list of
// reviewable explanations, the detail frame for the one the address names,
// provenance (the detail half of ai-010), and the affected area on a map
// zoomed to it (qa.md 164). Every value below is shaped like a stored row; the
// aircraft are invented.

const summary = (over: Partial<HypothesisSummary> = {}): HypothesisSummary => ({
  id: 104,
  bundleId: 250,
  runId: 106,
  hypothesisTitle: "Possible interference zone affecting RF-04 and RF-05",
  confidence: "Medium",
  status: "New",
  generator: "hosted",
  requestedGenerator: "hosted",
  fellBack: false,
  modelId: "gpt-4.1-2025-04-14",
  anomalyType: "possible_interference_zone",
  ruleId: "FUSION-SPATIAL",
  subject: "RF-04, RF-05",
  windowStart: "2022-06-27T12:09:46Z",
  windowEnd: "2022-06-27T12:14:56Z",
  latestVerdict: null,
  ...over,
});

const FAULT_SUMMARY = summary({
  id: 148,
  bundleId: 290,
  runId: 160,
  hypothesisTitle: "Possible receiver fault on RF-06",
  anomalyType: "possible_sensor_fault",
  ruleId: "SENSOR-FAULT",
  subject: "RF-06",
  windowStart: "2022-06-27T12:09:01Z",
  windowEnd: "2022-06-27T12:13:51Z",
});

const LIST: HypothesisList = { hypotheses: [summary(), FAULT_SUMMARY], unreviewableBundles: 0 };

const detail = (over: Partial<HypothesisDetail> = {}): HypothesisDetail => ({
  id: 104,
  bundleId: 250,
  reviewable: true,
  hypothesisTitle: "Possible interference zone affecting RF-04 and RF-05",
  confidence: "Medium",
  summary: "Both RF-04 and RF-05 recorded repeated power deviations while aircraft nearby lost contact.",
  supportingEvidence: [
    {
      position: 1,
      ruleId: "RF-NOISE",
      findingType: "rf_noise_deviation",
      statement: "Both RF-04 and RF-05 recorded repeated, significant power_dbm deviations.",
      grounding: "grounded",
    },
  ],
  evidenceAgainstOrUncertainty: ["Track discontinuities near the area are common in normal traffic."],
  alternativeExplanations: ["Two receivers degrading at once from a shared hardware cause."],
  recommendedHumanAction: "Check RF-04 and RF-05 against a nearby independent receiver before acting.",
  generator: "hosted",
  requestedGenerator: "hosted",
  fellBack: false,
  modelId: "gpt-4.1-2025-04-14",
  status: "New",
  grounding: "passed",
  bundle: {
    runId: 106,
    anomalyType: "possible_interference_zone",
    ruleId: "FUSION-SPATIAL",
    subject: "RF-04, RF-05",
    windowStart: "2022-06-27T12:09:46Z",
    windowEnd: "2022-06-27T12:14:56Z",
    longitude: 5.758,
    latitude: 51.526,
    channels: [3, 4],
    receivers: ["RF-04", "RF-05"],
  },
  verdicts: [],
  ...over,
});

const FAULT = detail({
  id: 148,
  bundleId: 290,
  hypothesisTitle: "Possible receiver fault on RF-06",
  bundle: {
    runId: 160,
    anomalyType: "possible_sensor_fault",
    ruleId: "SENSOR-FAULT",
    subject: "RF-06",
    windowStart: "2022-06-27T12:09:01Z",
    windowEnd: "2022-06-27T12:13:51Z",
    longitude: 6.767,
    latitude: 51.289,
    channels: [2],
    receivers: ["RF-05", "RF-06", "RF-07"],
  },
});

const sensor = (id: string, lat: number, lon: number, health: RFSensor["health"] = "nominal"): RFSensor => ({
  ...operationalPictureMock.rfSensors[0],
  id,
  lat,
  lon,
  health,
});

const ZONE: InterferenceZone = {
  id: "event-77",
  confidence: "Medium",
  corroboration: "corroborated",
  centre: { lat: 51.526, lon: 5.758 },
  radiusKm: 60,
  receivers: ["RF-04", "RF-05"],
  // The picture serialises its own way; a match is on the instant, not the string.
  startedAt: "2022-06-27T12:09:46+00:00",
  endedAt: "2022-06-27T12:14:56+00:00",
};

const picture = (over: Partial<OperationalPicture> = {}): OperationalPicture => ({
  ...operationalPictureMock,
  rfSensors: [
    sensor("RF-03", 52.4, 5.1),
    sensor("RF-04", 51.45, 5.375, "degraded"),
    sensor("RF-05", 51.6, 6.14, "degraded"),
    sensor("RF-06", 51.289, 6.767, "fault"),
    sensor("RF-07", 50.866, 7.143),
  ],
  interferenceZones: [ZONE],
  ...over,
});

const never = <T,>() => new Promise<T>(() => {});

interface Loaders {
  loadList: () => Promise<HypothesisList>;
  loadDetail: (id: number) => Promise<HypothesisDetail>;
  loadPicture: (runId: number) => Promise<OperationalPicture>;
  submitVerdict: (id: number, request: VerdictRequest) => Promise<HypothesisDetail>;
}

const show = (hypothesisId: number | null, over: Partial<Loaders> = {}) => {
  const loaders: Loaders = {
    loadList: () => Promise.resolve(LIST),
    loadDetail: (id) => Promise.resolve(id === 148 ? FAULT : detail()),
    loadPicture: () => Promise.resolve(picture()),
    submitVerdict: never,
    ...over,
  };
  const view = render(
    <HypothesesScreen
      hypothesisId={hypothesisId}
      {...loaders}
    />,
  );
  return {
    ...view,
    goTo: (id: number | null) =>
      view.rerender(
        <HypothesesScreen
          hypothesisId={id}
          {...loaders}
        />,
      ),
  };
};

const list = () => within(screen.getByRole("navigation", { name: "Explanations" }));
const header = () => within(screen.getByRole("heading", { level: 2 }).closest("header") as HTMLElement);
// The region exists once the explanation has loaded, so it is waited for.
const mapRegion = async () => within(await screen.findByRole("region", { name: "Affected area" }));

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("the list to choose from (hyp-001 (1))", () => {
  it("lists every reviewable explanation as a link to its own address", async () => {
    show(null);

    expect(await list().findByRole("link", { name: /interference zone affecting RF-04/i })).toHaveAttribute("href", "#/hypotheses/104");
    expect(list().getByRole("link", { name: /receiver fault on RF-06/i })).toHaveAttribute("href", "#/hypotheses/148");
  });

  it("shows each entry's status and window", async () => {
    show(null);

    const entry = await list().findByRole("link", { name: /receiver fault on RF-06/i });
    expect(within(entry).getByText("New")).toBeInTheDocument();
    expect(within(entry).getByText("12:09:01–12:13:51 UTC")).toBeInTheDocument();
  });

  it("marks the open explanation as the current one, and only that one", async () => {
    show(148);

    expect(await list().findByRole("link", { name: /receiver fault on RF-06/i })).toHaveAttribute("aria-current", "page");
    expect(list().getByRole("link", { name: /interference zone affecting/i })).not.toHaveAttribute("aria-current");
  });

  it("asks for a choice when the address names no explanation", async () => {
    show(null);

    expect(await screen.findByText(/choose an explanation from the list/i)).toBeInTheDocument();
  });

  it("says the list is empty, and counts the conclusions with nothing under review", async () => {
    // Failure case: an empty list must not read as a list still loading.
    show(null, { loadList: () => Promise.resolve({ hypotheses: [], unreviewableBundles: 3 }) });

    expect(await screen.findByText(/no explanations are stored for review/i)).toBeInTheDocument();
    expect(screen.getByText(/3 conclusions have explanations, but none is the one under review/i)).toBeInTheDocument();
  });

  it("says so when the list cannot be loaded, and still opens the explanation asked for", async () => {
    show(104, { loadList: () => Promise.reject(new Error("503")) });

    expect(await screen.findByText(/the list of explanations could not be loaded/i)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: /interference zone affecting RF-04/i })).toBeInTheDocument();
  });
});

describe("the detail's header (hyp-001 (2))", () => {
  it("shows the title, status, confidence, window and run", async () => {
    show(104);

    await screen.findByRole("heading", { level: 2, name: /interference zone affecting RF-04 and RF-05/i });
    expect(header().getByText("New")).toBeInTheDocument();
    // Through the ui-001 primitive: the label and its value as a definition.
    expect(header().getByText("Confidence").nextElementSibling).toHaveTextContent("Medium");
    expect(header().getByText("12:09:46–12:14:56 UTC")).toBeInTheDocument();
    expect(header().getByText(/run 106/i)).toBeInTheDocument();
  });

  it("states the affected area as what is stored: the subject, the receivers named and the centre", async () => {
    // Never an invented sector or zone name (the design's "Sector A / Zone AZ-402").
    show(104);

    await screen.findByRole("heading", { level: 2 });
    expect(header().getByText("RF-04, RF-05")).toBeInTheDocument();
    expect(header().getByText(/51\.526° N, 5\.758° E/)).toBeInTheDocument();
  });

  it("never shows a percentage", async () => {
    show(104);

    await screen.findByRole("heading", { level: 2 });
    expect(document.body.textContent).not.toMatch(/\d\s*%/);
  });
});

describe("who wrote it (hyp-001 (3), the detail half of ai-010)", () => {
  it("names the AI model by its stored id", async () => {
    show(104);

    expect(await screen.findByText("Written by the AI model, gpt-4.1-2025-04-14")).toBeInTheDocument();
  });

  it("names the template as the writer of a template row", async () => {
    show(104, { loadDetail: () => Promise.resolve(detail({ generator: "template", requestedGenerator: "template", modelId: null })) });

    expect(await screen.findByText("Written by the template")).toBeInTheDocument();
  });

  it("shows a fallback naming both arms, distinguishable from a primary answer", async () => {
    // ai-010's failure case: a fallback rendering identically to a hosted answer.
    show(104, { loadDetail: () => Promise.resolve(detail({ generator: "template", fellBack: true, modelId: null })) });

    expect(await screen.findByText("The AI model's answer was not used; the template's is shown instead")).toBeInTheDocument();
    expect(screen.queryByText(/written by the ai model/i)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/gpt/i);
  });
});

describe("the summary, the action and the verdicts (hyp-001 (4), (5))", () => {
  it("shows the summary and the recommended action under their own headings", async () => {
    show(104);

    const summaryHeading = await screen.findByRole("heading", { name: "Summary" });
    expect(summaryHeading.parentElement).toHaveTextContent(detail().summary);
    expect(screen.getByRole("heading", { name: "Recommended action" }).parentElement).toHaveTextContent(detail().recommendedHumanAction);
  });

  it("says so when no verdict has been recorded", async () => {
    show(104);

    expect(await screen.findByText(/no verdict recorded yet/i)).toBeInTheDocument();
  });

  it("lists the verdicts oldest first, each with its note and time", async () => {
    show(104, {
      loadDetail: () =>
        Promise.resolve(
          detail({
            verdicts: [
              { verdict: "needs-more-evidence", note: "Want RF-03's readings.", createdAt: "2026-10-11T09:00:00Z" },
              { verdict: "confirm", note: null, createdAt: "2026-10-11T10:30:00Z" },
            ],
          }),
        ),
    });

    const history = within((await screen.findByRole("heading", { name: "Verdicts" })).parentElement as HTMLElement);
    const items = history.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    // In words since fbk-001 (amended 2026-10-13); the stored value was shown raw before.
    expect(items[0]).toHaveTextContent("Needs more evidence");
    expect(items[0]).toHaveTextContent("Want RF-03's readings.");
    expect(items[0]).toHaveTextContent("09:00:00 UTC");
    expect(items[1]).toHaveTextContent("Confirm");
    expect(history.queryByText(/no verdict recorded yet/i)).not.toBeInTheDocument();
  });
});

describe("the states that are not an explanation (hyp-001 failure cases)", () => {
  it("names an id the store does not hold, never an empty header", async () => {
    show(999, { loadDetail: () => Promise.reject(new HypothesisNotFoundError(999)) });

    expect(await screen.findByText(/there is no explanation 999 in the store/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
  });

  it("says so when the explanation cannot be loaded, never a blank workspace", async () => {
    show(104, { loadDetail: () => Promise.reject(new Error("500")) });

    expect(await screen.findByText(/explanation 104 could not be loaded/i)).toBeInTheDocument();
  });

  it("says it is loading the explanation asked for, while it loads", () => {
    show(104, { loadDetail: never });

    expect(screen.getByText(/loading explanation 104/i)).toBeInTheDocument();
  });

  it("never leaves the previous explanation under a new address", async () => {
    let answer: (value: HypothesisDetail) => void = () => {};
    const view = show(104, {
      loadDetail: (id) => (id === 104 ? Promise.resolve(detail()) : new Promise((resolve) => (answer = resolve))),
    });
    await screen.findByRole("heading", { level: 2, name: /interference zone/i });

    view.goTo(148);

    expect(screen.queryByRole("heading", { level: 2, name: /interference zone/i })).not.toBeInTheDocument();
    expect(screen.getByText(/loading explanation 148/i)).toBeInTheDocument();
    await act(async () => answer(FAULT));
    expect(screen.getByRole("heading", { level: 2, name: /receiver fault on RF-06/i })).toBeInTheDocument();
  });

  it("refuses an answer naming another explanation than the address asked for", async () => {
    show(148, { loadDetail: () => Promise.resolve(detail()) });

    expect(await screen.findByText(/explanation 148 could not be loaded/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /interference zone/i })).not.toBeInTheDocument();
  });

  it("drops a slow answer for an address no longer on screen", async () => {
    let late: (value: HypothesisDetail) => void = () => {};
    const view = show(104, {
      loadDetail: (id) => (id === 104 ? new Promise((resolve) => (late = resolve)) : Promise.resolve(FAULT)),
    });
    view.goTo(148);
    await screen.findByRole("heading", { level: 2, name: /receiver fault/i });

    await act(async () => late(detail()));

    expect(screen.getByRole("heading", { level: 2, name: /receiver fault/i })).toBeInTheDocument();
  });
});

describe("the affected area on a map (hyp-001 (6), qa.md 164)", () => {
  it("draws an interference conclusion's zone and only the receivers its evidence names, with no aircraft", async () => {
    show(104);

    expect(await (await mapRegion()).findByText("zones: event-77")).toBeInTheDocument();
    expect((await mapRegion()).getByText("receivers: RF-04, RF-05")).toBeInTheDocument();
    expect((await mapRegion()).getByText("aircraft:")).toBeInTheDocument();
  });

  it("keeps each receiver's state from the hour's picture", async () => {
    show(104);

    expect(await (await mapRegion()).findByText("receiver states: RF-04 degraded; RF-05 degraded")).toBeInTheDocument();
  });

  it("zooms to the area, not the corpus", async () => {
    show(104);

    const expected = affectedAreaBounds({ lat: 51.526, lon: 5.758 }, 60, [
      { lat: 51.45, lon: 5.375 },
      { lat: 51.6, lon: 6.14 },
    ]);
    expect(await (await mapRegion()).findByText(`bounds: ${JSON.stringify(expected)}`)).toBeInTheDocument();
  });

  it("prints the centre's latitude and longitude under the map", async () => {
    show(104);

    expect(await (await mapRegion()).findByText(/51\.526° N, 5\.758° E/)).toBeInTheDocument();
  });

  it("asks for the conclusion's own hour, unfiltered", async () => {
    const loadPicture = vi.fn(() => Promise.resolve(picture()));
    show(104, { loadPicture });

    await (await mapRegion()).findByText("zones: event-77");
    expect(loadPicture).toHaveBeenCalledWith(106);
  });

  it("draws no disc for a receiver fault, and says a fault is not an area", async () => {
    show(148);

    expect(await (await mapRegion()).findByText(/a claim about RF-06, not an area, so no area is drawn/i)).toBeInTheDocument();
    expect((await mapRegion()).getByText("zones:")).toBeInTheDocument();
    expect((await mapRegion()).getByText("receivers: RF-05, RF-06, RF-07")).toBeInTheDocument();
  });

  it("draws no disc, and says why, when the claim recorded no radius", async () => {
    // Failure case: never a default radius.
    show(104, { loadPicture: () => Promise.resolve(picture({ interferenceZones: [{ ...ZONE, radiusKm: null }] })) });

    expect(await (await mapRegion()).findByText(/no radius was recorded with this claim, so no area is drawn/i)).toBeInTheDocument();
  });

  it("draws no disc, and says why, when the hour holds no zone matching the conclusion", async () => {
    show(104, { loadPicture: () => Promise.resolve(picture({ interferenceZones: [{ ...ZONE, receivers: ["RF-01", "RF-02"] }] })) });

    expect(await (await mapRegion()).findByText(/this conclusion's area is not on its hour's map, so no area is drawn/i)).toBeInTheDocument();
    expect((await mapRegion()).getByText("zones:")).toBeInTheDocument();
  });

  it("says so when the hour's map cannot be loaded, and the rest of the detail still renders", async () => {
    show(104, { loadPicture: () => Promise.reject(new Error("503")) });

    expect(await (await mapRegion()).findByText(/the map of this hour could not be loaded/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Summary" })).toBeInTheDocument();
    expect(screen.queryByTestId("map-view-stub")).not.toBeInTheDocument();
  });
});

describe("placing the affected area (hyp-001 (6))", () => {
  const centre = { lat: 51.526, lon: 5.758 };

  it("fits the whole disc at the assessed radius", () => {
    const [[west, south], [east, north]] = affectedAreaBounds(centre, 60, []);
    // 60 km is 0.5390° of latitude, and 0.866° of longitude at 51.5° N; to four places, rounded down.
    expect(south).toBeLessThanOrEqual(51.526 - 0.5389);
    expect(north).toBeGreaterThanOrEqual(51.526 + 0.5389);
    expect(west).toBeLessThanOrEqual(5.758 - 0.8659);
    expect(east).toBeGreaterThanOrEqual(5.758 + 0.8659);
    // Zoomed to the area, not padded out to the corpus.
    expect(north - south).toBeLessThan(1.5);
  });

  it("takes in a named receiver outside the disc", () => {
    const [[west]] = affectedAreaBounds(centre, 60, [{ lat: 51.5, lon: 4.5 }]);
    expect(west).toBeLessThanOrEqual(4.5);
  });

  it("never fits a box of no size, with no radius and one point", () => {
    const [[west, south], [east, north]] = affectedAreaBounds({ lat: 51.289, lon: 6.767 }, null, [{ lat: 51.289, lon: 6.767 }]);
    expect(east).toBeGreaterThan(west);
    expect(north).toBeGreaterThan(south);
  });

  const conclusion = detail().bundle;

  it("matches the zone with the conclusion's receivers and window, on the instant", () => {
    expect(matchZone(conclusion, [ZONE])).toBe(ZONE);
  });

  it.each([
    ["other receivers", { receivers: ["RF-04", "RF-06"] }],
    ["another window", { startedAt: "2022-06-27T12:24:40Z" }],
    // Added after the mutation pass: a zone holding only some of the conclusion's receivers.
    ["only some of its receivers", { receivers: ["RF-04"] }],
  ])("matches no zone with %s", (_, over) => {
    expect(matchZone(conclusion, [{ ...ZONE, ...over }])).toBeNull();
  });

  it("matches no zone when two match, rather than choosing one", () => {
    expect(matchZone(conclusion, [ZONE, { ...ZONE, id: "event-78" }])).toBeNull();
  });

  it("matches receivers as a set, not as a sequence", () => {
    expect(matchZone(conclusion, [{ ...ZONE, receivers: ["RF-05", "RF-04"] }])).not.toBeNull();
  });
});

describe("where the screen's data comes from (hyp-001 input)", () => {
  const respond = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

  it("asks the list endpoint for the list", async () => {
    const fetchMock = vi.fn(() => respond(200, LIST));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchHypotheses()).resolves.toEqual(LIST);
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toBe(HYPOTHESES_PATH);
    expect(HYPOTHESES_PATH).toBe("/api/v1/hypotheses");
  });

  it("asks the detail endpoint for one explanation", async () => {
    const fetchMock = vi.fn(() => respond(200, detail()));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchHypothesis(104)).resolves.toEqual(detail());
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toBe("/api/v1/hypotheses/104");
  });

  it("tells a 404 apart from any other failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => respond(404, { detail: "no hypothesis 999 in the store" })),
    );
    await expect(fetchHypothesis(999)).rejects.toBeInstanceOf(HypothesisNotFoundError);

    vi.stubGlobal(
      "fetch",
      vi.fn(() => respond(500, {})),
    );
    const failure = fetchHypothesis(104);
    await expect(failure).rejects.toThrow();
    await expect(failure).rejects.not.toBeInstanceOf(HypothesisNotFoundError);
  });

  it.each([
    ["the list", () => fetchHypotheses()],
    ["the detail", () => fetchHypothesis(104)],
  ])("refuses an answer that is not %s", async (_, call) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => respond(200, { something: "else" })),
    );
    await expect(call()).rejects.toThrow();
  });

  it("is wired through the seam: an explanation's address fetches it and shows it", async () => {
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/v1/hypotheses") return respond(200, LIST);
      if (path === "/api/v1/hypotheses/104") return respond(200, detail());
      if (path.includes("operational-picture/hours")) return respond(200, []);
      if (path.includes("operational-picture")) return respond(200, picture());
      return respond(200, { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);
    window.location.hash = "#/hypotheses/104";

    render(<App />);

    expect(await screen.findByRole("heading", { level: 2, name: /interference zone affecting RF-04/i })).toBeInTheDocument();
    // The conclusion's hour unfiltered: a filtered view could withhold a receiver the evidence names.
    // The view assertion was added after the mutation pass.
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([path]) => String(path).includes("run=106") && String(path).includes("view=all"))).toBe(true),
    );
    // The screen fetches through what the seam hands it: no mock, no network of its own.
    expect(screenSource).not.toMatch(/mocks\//);
    expect(screenSource).not.toMatch(/\bfetch\s*\(/);
  });
});
