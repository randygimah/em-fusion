import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { DEFAULT_POLL_INTERVAL_MS } from "../lib/api";
import operationalPicture from "../mocks/operationalPictureMock";
import { SCREENS } from "../routes";

// The screen each destination is recognised by. The Operational Picture's own
// heading carries the scenario name, which is data, so it is identified by the
// panel that only it has.
const OPERATIONAL_PICTURE = /detection summary/i;

const rail = () => within(screen.getByRole("navigation", { name: /screens/i }));

const goTo = (label: RegExp) => fireEvent.click(rail().getByRole("link", { name: label }));

const addressOf = (id: string): string => SCREENS.find((screenRoute) => screenRoute.id === id)?.hash ?? "";

beforeEach(() => {
  // jsdom keeps the URL between renders in a file, and the hash is the route.
  window.location.hash = "";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("the navigation shell", () => {
  it("declares exactly three screens, each with its own address", () => {
    // spec: nav-001, FR-701 — the closed set at its source. Two lists would be
    // two places to add a fourth, and only one of them would be tested.
    expect(SCREENS.map((screenRoute) => screenRoute.label)).toEqual([
      "Operational Picture",
      "Hypotheses",
      "Scenario Control",
    ]);
    expect(new Set(SCREENS.map((screenRoute) => screenRoute.hash)).size).toBe(3);
  });

  it("renders exactly three navigation entries and no fourth", () => {
    // spec: nav-001, FR-701 — drill-down tables and system health are not
    // entries, so the count is the assertion.
    render(<App />);

    const entries = rail().getAllByRole("link");

    expect(entries).toHaveLength(3);
    for (const label of [/operational picture/i, /hypotheses/i, /scenario control/i]) {
      expect(rail().getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("marks exactly one entry as the current page", () => {
    // spec: nav-001, FR-709, US-A1 — zero active entries on a known route
    // fails the item, and so does more than one: the rail would then be
    // telling assistive technology the analyst is in two places at once.
    render(<App />);

    const current = rail()
      .getAllByRole("link")
      .filter((entry) => entry.getAttribute("aria-current") === "page");

    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAccessibleName(/operational picture/i);
  });

  it("shows the Scenario Control screen when its entry is chosen", async () => {
    // spec: nav-001, scn-004 — the screen landed with its own tests and no way
    // to reach it. This is the test that says it is reachable.
    render(<App />);

    goTo(/scenario control/i);

    expect(await screen.findByRole("table", { name: /recent runs/i })).toBeInTheDocument();
    expect(screen.queryByText(OPERATIONAL_PICTURE)).not.toBeInTheDocument();
  });

  it("moves the current-page marker to the screen it navigated to", async () => {
    // spec: nav-001 — the rail and the workspace must never disagree about
    // which screen the analyst is on.
    render(<App />);

    goTo(/scenario control/i);
    await screen.findByRole("table", { name: /recent runs/i });

    expect(rail().getByRole("link", { name: /scenario control/i })).toHaveAttribute("aria-current", "page");
    expect(rail().getByRole("link", { name: /operational picture/i })).not.toHaveAttribute("aria-current");
  });

  it("opens on the screen named in the address it was given", () => {
    // spec: nav-001 (first decision) — the point of putting the route in the
    // URL rather than in component state: a reload returns the analyst to the
    // screen they chose, and a screen can be linked to.
    window.location.hash = addressOf("scenario-control");

    render(<App />);

    expect(screen.getByRole("table", { name: /recent runs/i })).toBeInTheDocument();
  });

  it("falls back to the Operational Picture when the address names no screen", () => {
    // spec: nav-001 (first decision) — an unrecognised hash rendering nothing
    // is a blank workspace with a nav rail above it, which reads as a broken
    // app rather than as a bad link.
    window.location.hash = "#/nowhere";

    render(<App />);

    expect(screen.getByText(OPERATIONAL_PICTURE)).toBeInTheDocument();
    expect(rail().getByRole("link", { name: /operational picture/i })).toHaveAttribute("aria-current", "page");
  });

  it("says the Hypotheses screen is not built rather than rendering nothing", async () => {
    // spec: nav-001 (second decision), FR-701 — the rail has three entries
    // because the specification fixes three, and the third has no screen yet.
    // An entry leading to a blank page names nothing; this one names the gap.
    render(<App />);

    goTo(/hypotheses/i);

    expect(await screen.findByText(/not built yet/i)).toBeInTheDocument();
  });

  // Removed 2026-09-13, superseded by api-010 rather than deleted for being
  // inconvenient. nav-001's third decision put a sentence on screen saying the
  // listed runs were a fixture, which was true while api-006 did not exist.
  // The runs now come from the database, so the sentence would be false and
  // the note is gone. The principle it expressed is asserted in the other
  // direction in scenarioAccess.test.tsx: the word "fixture" must be absent
  // once the rows are real.

  it("stops polling the picture when the analyst leaves it", async () => {
    // spec: nav-001 (fourth decision), api-003 — the hook belongs to the
    // screen that needs it. Left in App it would poll every five seconds
    // against an endpoint whose data is not on screen.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => operationalPicture,
    } as Response);
    vi.stubGlobal("fetch", fetchMock);
    vi.useFakeTimers();

    // Counted by path rather than in total. Since api-010 the Scenario Control
    // screen polls an endpoint of its own, so a bare call count keeps rising
    // after the analyst leaves the picture and would fail this test for the
    // opposite of the reason it exists.
    const pictureCalls = () =>
      fetchMock.mock.calls.filter(([path]) => String(path).includes("operational-picture")).length;

    render(<App />);
    await vi.advanceTimersByTimeAsync(DEFAULT_POLL_INTERVAL_MS * 2);
    const polled = pictureCalls();

    goTo(/scenario control/i);
    await vi.advanceTimersByTimeAsync(DEFAULT_POLL_INTERVAL_MS * 3);

    expect(polled).toBeGreaterThan(0);
    expect(pictureCalls()).toBe(polled);
  });
});
