import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EmEvidencePanel } from "../components/em/EmEvidencePanel";
import { EVIDENCE_COLLAPSED_KEY } from "../hooks/useEvidenceCollapsed";
import type {
  EvidenceAccount,
  ExplainedClaim,
  UnclaimedBundle,
  UnexplainedClaim,
} from "../types/evidence";

// spec: op-010 (amended 2026-10-06) — the panel is collapsible, and collapsed
// its header still states what is inside: how many conclusions this hour holds
// and how many have no stored evidence. A collapse that hid that would turn the
// gap the panel exists to expose into something an analyst has to go looking
// for — op-003's dash in a new costume. Expanded by default; the preference is
// the analyst's chrome and lives in guarded localStorage, never the hash.

const explained = (bundleId: number): ExplainedClaim => ({
  bundleId,
  ruleId: "SENSOR-FAULT",
  findingType: "possible_sensor_fault",
  subject: `RF-0${bundleId}`,
  observedFrom: "2022-06-27T12:31:22+00:00",
  observedTo: "2022-06-27T12:36:52+00:00",
  lat: 51.5,
  lon: 6.0,
  channels: [4],
  dataModes: ["synthetic"],
  evidence: [
    {
      ruleId: "RF-NOISE",
      findingType: "rf_noise_deviation",
      grounding: "observed",
      dataMode: "synthetic",
      count: 1,
      observedFrom: "2022-06-27T12:31:22+00:00",
      observedTo: "2022-06-27T12:36:52+00:00",
      sources: ["RF-06:4"],
      statements: [{ text: "power_dbm deviated by 8.40 dB at its peak", count: 1, sources: ["RF-06:4"] }],
    },
  ],
  uncertainties: [],
  superseded: [],
});

const unexplained: UnexplainedClaim = {
  ruleId: "FUSION-SPATIAL",
  findingType: "possible_interference_zone",
  subject: "RF-01",
  observedFrom: "2022-06-27T12:22:13+00:00",
  observedTo: "2022-06-27T12:27:53+00:00",
  reason: "not-bundled",
};

const unclaimed: UnclaimedBundle = {
  bundleId: 251,
  ruleId: "SENSOR-FAULT",
  findingType: "possible_sensor_fault",
  subject: "RF-05",
  observedFrom: "2022-06-27T12:37:07+00:00",
  observedTo: "2022-06-27T12:42:07+00:00",
  reason: "no-current-claim",
};

const account = (over: Partial<EvidenceAccount> = {}): EvidenceAccount => ({
  runId: 102,
  explained: [],
  unexplained: [],
  unclaimed: [],
  ...over,
});

const panel = () => screen.getByRole("region", { name: "Evidence" });
const toggle = () => within(panel()).getByRole("button", { name: /evidence/i });
const header = () => within(panel()).getByRole("heading", { name: /evidence/i, level: 2 });

beforeEach(() => {
  window.localStorage.clear();
  window.location.hash = "";
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("collapsing the evidence panel", () => {
  it("opens expanded, and says so", () => {
    // spec: op-010 — expanded by default: the panel is the project's own
    // subject, and one collapsed by default is one nobody opens.
    render(<EmEvidencePanel account={account({ explained: [explained(1)] })} />);

    expect(toggle()).toHaveAttribute("aria-expanded", "true");
    expect(within(panel()).getByRole("list", { name: "Supporting evidence" })).toBeInTheDocument();
  });

  it("hides the evidence when collapsed and offers the way back", () => {
    // spec: op-010 — a control the analyst can leave in either direction.
    render(<EmEvidencePanel account={account({ explained: [explained(1)] })} />);

    fireEvent.click(toggle());

    expect(toggle()).toHaveAttribute("aria-expanded", "false");
    expect(within(panel()).queryByRole("list", { name: "Supporting evidence" })).toBeNull();

    fireEvent.click(toggle());

    expect(within(panel()).getByRole("list", { name: "Supporting evidence" })).toBeInTheDocument();
  });
});

describe("what a collapsed header still says", () => {
  it("counts the conclusions and those with no stored evidence", () => {
    // spec: op-010 — the one constraint that is the whole of the amendment.
    render(
      <EmEvidencePanel
        account={account({ explained: [explained(1), explained(2)], unexplained: [unexplained] })}
      />,
    );

    fireEvent.click(toggle());

    expect(header()).toHaveTextContent("3 conclusions");
    expect(header()).toHaveTextContent("1 with no stored evidence");
  });

  it("states a zero rather than leaving the count out", () => {
    // spec: op-010 — "none lack evidence" is a finding; an absent count reads
    // as one nobody took.
    render(<EmEvidencePanel account={account({ explained: [explained(1)] })} />);

    fireEvent.click(toggle());

    expect(header()).toHaveTextContent("1 conclusion");
    expect(header()).not.toHaveTextContent("1 conclusions");
    expect(header()).toHaveTextContent("0 with no stored evidence");
  });

  it("tells an hour with an unexplained conclusion apart from a quiet one", () => {
    // spec: op-010 failure case — "a collapsed header that says only
    // Evidence, so an hour with an unexplained conclusion is indistinguishable
    // from a quiet one".
    const { unmount } = render(
      <EmEvidencePanel account={account({ unexplained: [unexplained] })} />,
    );
    fireEvent.click(toggle());
    const gap = header().textContent;
    unmount();

    render(<EmEvidencePanel account={account()} />);
    const quiet = header().textContent;

    expect(quiet).toMatch(/no conclusions/i);
    expect(gap).not.toEqual(quiet);
    expect(gap).toMatch(/1 with no stored evidence/);
  });

  it.each([
    ["loading", /loading/i],
    ["failed", /could not be loaded/i],
    [null, /not examined/i],
  ] as const)("names the state when there is no account to count (%s)", (state, words) => {
    // spec: op-010 — the five states stay five when collapsed: no count is
    // invented for an hour whose account the panel does not have.
    render(<EmEvidencePanel account={state} />);

    fireEvent.click(toggle());

    expect(header()).toHaveTextContent(words);
    expect(header()).not.toHaveTextContent(/conclusion/i);
  });

  it("keeps the unclaimed-evidence note visible", () => {
    // spec: op-010 failure case — "a collapse that also hides the
    // unclaimed-evidence note, which is a fact about the hour whatever the
    // conclusions look like".
    render(
      <EmEvidencePanel account={account({ explained: [explained(1)], unclaimed: [unclaimed] })} />,
    );

    fireEvent.click(toggle());

    expect(panel()).toHaveTextContent(/does not match any conclusion/);
  });
});

describe("where the preference is kept", () => {
  it("survives a remount, as a preference should", () => {
    // spec: op-010, nav-003 — guarded localStorage, per browser.
    const { unmount } = render(<EmEvidencePanel account={account()} />);
    fireEvent.click(toggle());
    unmount();

    render(<EmEvidencePanel account={account()} />);

    expect(toggle()).toHaveAttribute("aria-expanded", "false");
    expect(window.localStorage.getItem(EVIDENCE_COLLAPSED_KEY)).toBe("collapsed");
  });

  it("never touches the address", () => {
    // spec: op-010 — the state is chrome, not the route, so it stays out of
    // the hash nav-001 owns.
    render(<EmEvidencePanel account={account()} />);

    fireEvent.click(toggle());

    expect(window.location.hash).toBe("");
  });

  it("resolves an unexpected stored value to expanded", () => {
    // spec: op-010 — the safe direction is the one that shows more.
    window.localStorage.setItem(EVIDENCE_COLLAPSED_KEY, "true");

    render(<EmEvidencePanel account={account()} />);

    expect(toggle()).toHaveAttribute("aria-expanded", "true");
  });

  it("opens expanded when storage cannot be read", () => {
    // spec: op-010 — a private window with site data blocked throws on access.
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    render(<EmEvidencePanel account={account()} />);

    expect(toggle()).toHaveAttribute("aria-expanded", "true");
  });

  it("still collapses when storage cannot be written", () => {
    // spec: op-010 — a preference that cannot be saved lasts one visit; it is
    // not a failure to surface.
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    render(<EmEvidencePanel account={account()} />);
    fireEvent.click(toggle());

    expect(toggle()).toHaveAttribute("aria-expanded", "false");
  });
});
