import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { HYPOTHESES_PATH, postVerdict } from "../lib/api";
import operationalPictureMock from "../mocks/operationalPictureMock";
import HypothesesScreen from "../screens/hypotheses";
import screenSource from "../screens/hypotheses.tsx?raw";
import type { HypothesisDetail, HypothesisList, HypothesisSummary, ReviewStatus, Verdict, VerdictRequest } from "../types/hypotheses";

// spec: fbk-001, fbk-002, hyp-004 (amended 2026-10-13) — the verdict card on
// the Hypotheses screen: four buttons posting to api-005, an optional note, the
// reply as stored shown as the store holds it, a failure changing nothing, and
// the decision-support line always present. Values are shaped like stored rows.

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

const LIST: HypothesisList = {
  hypotheses: [summary(), summary({ id: 148, bundleId: 290, runId: 160, hypothesisTitle: "Possible receiver fault on RF-06" })],
  unreviewableBundles: 0,
};

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
  evidenceAgainstOrUncertainty: [],
  alternativeExplanations: [],
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

const FAULT = detail({ id: 148, bundleId: 290, hypothesisTitle: "Possible receiver fault on RF-06" });

/** What the store answers after a verdict: the detail with its new status and the verdict appended. */
const stored = (verdict: Verdict, status: ReviewStatus, note: string | null = null, over: Partial<HypothesisDetail> = {}) =>
  detail({ status, verdicts: [{ verdict, note, createdAt: "2026-10-13T09:00:00Z" }], ...over });

const DISCLAIMER = "Decision support only — analyst judgement is final.";
const BUTTONS = ["Confirm", "Reject", "Needs more evidence", "False positive"];

type Submit = (id: number, request: VerdictRequest) => Promise<HypothesisDetail>;

const show = (hypothesisId: number, submitVerdict: Submit, loadDetail = (id: number) => Promise.resolve(id === 148 ? FAULT : detail())) => {
  const props = {
    loadList: () => Promise.resolve(LIST),
    loadDetail,
    loadPicture: () => Promise.resolve(operationalPictureMock),
    submitVerdict,
  };
  const view = render(
    <HypothesesScreen
      hypothesisId={hypothesisId}
      {...props}
    />,
  );
  return {
    ...view,
    goTo: (id: number) =>
      view.rerender(
        <HypothesesScreen
          hypothesisId={id}
          {...props}
        />,
      ),
  };
};

const card = async () => within(await screen.findByRole("region", { name: "Analyst verdict" }));
const header = () => within(screen.getByRole("heading", { level: 2 }).closest("header") as HTMLElement);
const listEntry = (title: RegExp) => within(screen.getByRole("navigation", { name: "Explanations" })).getByRole("link", { name: title });
const history = () => within(screen.getByRole("heading", { name: "Verdicts" }).parentElement as HTMLElement);
const noteBox = (c: ReturnType<typeof within>) => c.getByRole("textbox", { name: /note/i }) as HTMLTextAreaElement;

/** A promise the test settles by hand. */
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("the verdict card (fbk-001)", () => {
  it("offers the four verdicts, in the design's order, under the affected-area map", async () => {
    show(104, vi.fn());

    const verdict = await card();
    expect(verdict.getAllByRole("button").map((button) => button.textContent?.trim())).toEqual(BUTTONS);
    const map = screen.getByRole("region", { name: "Affected area" });
    const region = screen.getByRole("region", { name: "Analyst verdict" });
    expect(map.compareDocumentPosition(region) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it.each([
    ["Confirm", "confirm"],
    ["Reject", "reject"],
    ["Needs more evidence", "needs-more-evidence"],
    ["False positive", "false-positive"],
  ] as const)("sends %s as %s in one click, with no confirmation step", async (label, verdict) => {
    const submit = vi.fn<Submit>(() => Promise.resolve(stored(verdict, "Confirmed")));
    show(104, submit);

    fireEvent.click((await card()).getByRole("button", { name: label }));

    expect(submit).toHaveBeenCalledTimes(1);
    expect(submit).toHaveBeenCalledWith(104, { verdict, note: null });
  });

  it("shows the status the store replied with, in the header, the list and the history", async () => {
    // The reply is the authority: here the store answers Rejected to a Confirm,
    // and the screen shows Rejected rather than working a status out itself.
    show(104, () => Promise.resolve(stored("confirm", "Rejected")));
    fireEvent.click((await card()).getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText(/verdict recorded\. the status is now rejected\./i)).toBeInTheDocument();
    expect(header().getByText("Rejected")).toBeInTheDocument();
    expect(listEntry(/interference zone affecting RF-04/i)).toHaveTextContent("Rejected");
    expect(history().getAllByRole("listitem")).toHaveLength(1);
    expect(history().getByRole("listitem")).toHaveTextContent("Confirm");
  });

  it("disables every button while a verdict is sending, and sends no second one", async () => {
    const pending = deferred<HypothesisDetail>();
    const submit = vi.fn<Submit>(() => pending.promise);
    show(104, submit);
    const verdict = await card();

    fireEvent.click(verdict.getByRole("button", { name: "Reject" }));

    expect(verdict.getByText(/recording the verdict/i)).toBeInTheDocument();
    for (const label of BUTTONS) expect(verdict.getByRole("button", { name: label })).toBeDisabled();
    fireEvent.click(verdict.getByRole("button", { name: "Confirm" }));
    expect(submit).toHaveBeenCalledTimes(1);

    await act(async () => pending.resolve(stored("reject", "Rejected")));
    for (const label of BUTTONS) expect(verdict.getByRole("button", { name: label })).toBeEnabled();
  });

  it("changes nothing when the verdict is refused, says so, and keeps the note", async () => {
    show(104, () => Promise.reject(new Error("/api/v1/hypotheses/104/feedback responded 409")));
    const verdict = await card();

    fireEvent.change(noteBox(verdict), { target: { value: "RF-03 quiet throughout." } });
    fireEvent.click(verdict.getByRole("button", { name: "Confirm" }));

    expect(await verdict.findByText(/the verdict was not recorded/i)).toBeInTheDocument();
    expect(header().getByText("New")).toBeInTheDocument();
    expect(listEntry(/interference zone affecting RF-04/i)).toHaveTextContent("New");
    expect(history().getByText(/no verdict recorded yet/i)).toBeInTheDocument();
    expect(noteBox(verdict).value).toBe("RF-03 quiet throughout.");
    for (const label of BUTTONS) expect(verdict.getByRole("button", { name: label })).toBeEnabled();
  });

  it("refuses a reply about another explanation as not recorded", async () => {
    show(104, () => Promise.resolve(stored("confirm", "Confirmed", null, { id: 105 })));
    fireEvent.click((await card()).getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText(/the verdict was not recorded/i)).toBeInTheDocument();
    expect(header().getByText("New")).toBeInTheDocument();
    expect(screen.queryByText(/verdict recorded\./i)).not.toBeInTheDocument();
  });

  it("offers no verdict on an explanation that is not the one under review", async () => {
    const submit = vi.fn<Submit>();
    show(105, submit, () => Promise.resolve(detail({ id: 105, reviewable: false })));

    const verdict = await card();
    expect(verdict.getByText(/takes no verdict/i)).toBeInTheDocument();
    expect(verdict.queryAllByRole("button")).toHaveLength(0);
    expect(verdict.queryByRole("textbox")).not.toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });

  it("starts fresh on another explanation, and a late reply for the last one does not land on it", async () => {
    const pending = deferred<HypothesisDetail>();
    const { goTo } = show(104, () => pending.promise);
    const first = await card();
    fireEvent.change(noteBox(first), { target: { value: "half-written" } });
    fireEvent.click(first.getByRole("button", { name: "Confirm" }));

    goTo(148);
    await screen.findByRole("heading", { level: 2, name: /receiver fault on RF-06/i });
    await act(async () => pending.resolve(stored("confirm", "Confirmed")));

    const second = await card();
    expect(noteBox(second).value).toBe("");
    expect(header().getByText("New")).toBeInTheDocument();
    expect(screen.queryByText(/verdict recorded\./i)).not.toBeInTheDocument();
    for (const label of BUTTONS) expect(second.getByRole("button", { name: label })).toBeEnabled();
  });

  it("names verdicts in the history in words, never the stored value", async () => {
    show(104, vi.fn(), () =>
      Promise.resolve(
        detail({
          verdicts: [
            { verdict: "needs-more-evidence", note: null, createdAt: "2026-10-11T09:00:00Z" },
            { verdict: "false-positive", note: null, createdAt: "2026-10-11T10:00:00Z" },
            { verdict: "inconclusive" as Verdict, note: null, createdAt: "2026-10-11T11:00:00Z" },
          ],
        }),
      ),
    );

    await card();
    const items = history().getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Needs more evidence");
    expect(items[1]).toHaveTextContent("False positive");
    expect(items[2]).toHaveTextContent(/unrecognised verdict/i);
    expect(history().queryByText(/needs-more-evidence|false-positive/)).not.toBeInTheDocument();
  });
});

describe("the note (fbk-002)", () => {
  it("sends the note typed with the verdict, and shows it under the verdict from the reply", async () => {
    const submit = vi.fn<Submit>((_, request) => Promise.resolve(stored(request.verdict, "Rejected", request.note)));
    show(104, submit);
    const verdict = await card();

    fireEvent.change(noteBox(verdict), { target: { value: "Shared mast; one cause." } });
    fireEvent.click(verdict.getByRole("button", { name: "Reject" }));

    expect(submit).toHaveBeenCalledWith(104, { verdict: "reject", note: "Shared mast; one cause." });
    expect(await history().findByText("Shared mast; one cause.")).toBeInTheDocument();
    expect(noteBox(verdict).value).toBe("");
  });

  it("sends a blank note as none: a note is never required", async () => {
    const submit = vi.fn<Submit>(() => Promise.resolve(stored("confirm", "Confirmed")));
    show(104, submit);
    const verdict = await card();

    fireEvent.change(noteBox(verdict), { target: { value: "   \n " } });
    fireEvent.click(verdict.getByRole("button", { name: "Confirm" }));

    expect(submit).toHaveBeenCalledWith(104, { verdict: "confirm", note: null });
  });

  it("counts the note against the limit, and over it blocks the verdict without cutting the text", async () => {
    const submit = vi.fn<Submit>();
    show(104, submit);
    const verdict = await card();
    expect(verdict.getByText("0 / 2,000 characters")).toBeInTheDocument();

    const long = "x".repeat(2001);
    fireEvent.change(noteBox(verdict), { target: { value: long } });

    expect(verdict.getByText("2,001 / 2,000 characters")).toBeInTheDocument();
    expect(verdict.getByText(/the note is over 2,000 characters/i)).toBeInTheDocument();
    expect(noteBox(verdict).value).toHaveLength(2001);
    expect(noteBox(verdict)).not.toHaveAttribute("maxlength");
    for (const label of BUTTONS) expect(verdict.getByRole("button", { name: label })).toBeDisabled();
    fireEvent.click(verdict.getByRole("button", { name: "Confirm" }));
    expect(submit).not.toHaveBeenCalled();

    fireEvent.change(noteBox(verdict), { target: { value: "x".repeat(2000) } });
    for (const label of BUTTONS) expect(verdict.getByRole("button", { name: label })).toBeEnabled();
  });
});

describe("the decision-support line (hyp-004)", () => {
  const disclaimer = async () => (await card()).getByText(DISCLAIMER);

  it("is visible text on the explanation under review, and nothing dismisses it", async () => {
    show(104, vi.fn());

    expect(await disclaimer()).toBeVisible();
    expect((await card()).queryByRole("button", { name: /dismiss|close|hide/i })).not.toBeInTheDocument();
  });

  it("is there on an explanation that takes no verdict", async () => {
    show(105, vi.fn(), () => Promise.resolve(detail({ id: 105, reviewable: false })));

    expect(await disclaimer()).toBeInTheDocument();
  });

  it("stays while sending, after a failure and after a recorded verdict", async () => {
    const pending = deferred<HypothesisDetail>();
    const submit = vi.fn<Submit>(() => pending.promise);
    show(104, submit);
    const verdict = await card();

    fireEvent.click(verdict.getByRole("button", { name: "Confirm" }));
    expect(verdict.getByText(DISCLAIMER)).toBeInTheDocument();

    await act(async () => pending.reject(new Error("offline")));
    expect(verdict.getByText(DISCLAIMER)).toBeInTheDocument();

    submit.mockImplementation(() => Promise.resolve(stored("confirm", "Confirmed")));
    fireEvent.click(verdict.getByRole("button", { name: "Confirm" }));
    await screen.findByText(/verdict recorded/i);
    expect(verdict.getByText(DISCLAIMER)).toBeInTheDocument();
  });
});

describe("where the verdict goes (fbk-001 output)", () => {
  const respond = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

  it("posts the verdict and the note as JSON to the explanation's feedback endpoint", async () => {
    const fetchMock = vi.fn((_path: string, _init?: RequestInit) => respond(200, stored("confirm", "Confirmed")));
    vi.stubGlobal("fetch", fetchMock);

    await expect(postVerdict(104, { verdict: "confirm", note: "seen" })).resolves.toEqual(stored("confirm", "Confirmed"));
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe(`${HYPOTHESES_PATH}/104/feedback`);
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toEqual({ verdict: "confirm", note: "seen" });
  });

  // The body is shaped like an explanation, so only the status can refuse it
  // (strengthened after the mutation pass).
  it.each([404, 409, 422, 500])("throws on a %s, whatever the body", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => respond(status, stored("confirm", "Confirmed"))),
    );
    await expect(postVerdict(104, { verdict: "confirm", note: null })).rejects.toThrow();
  });

  it("refuses an answer that is not an explanation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => respond(200, { something: "else" })),
    );
    await expect(postVerdict(104, { verdict: "confirm", note: null })).rejects.toThrow();
  });

  it("is wired through the seam: a click on the screen posts to the store", async () => {
    const fetchMock = vi.fn((path: string, _init?: RequestInit) => {
      if (path === "/api/v1/hypotheses") return respond(200, LIST);
      if (path === "/api/v1/hypotheses/104") return respond(200, detail());
      if (path === "/api/v1/hypotheses/104/feedback") return respond(200, stored("confirm", "Confirmed"));
      if (path.includes("operational-picture/hours")) return respond(200, []);
      if (path.includes("operational-picture")) return respond(200, operationalPictureMock);
      return respond(200, { status: "ok" });
    });
    vi.stubGlobal("fetch", fetchMock);
    window.location.hash = "#/hypotheses/104";

    render(<App />);
    fireEvent.click((await card()).getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([path, init]) => path === "/api/v1/hypotheses/104/feedback" && init?.method === "POST")).toBe(true),
    );
    expect(await screen.findByText(/verdict recorded/i)).toBeInTheDocument();
    expect(screenSource).not.toMatch(/\bfetch\s*\(/);
  });
});
