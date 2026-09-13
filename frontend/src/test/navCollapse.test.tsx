import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { RAIL_COLLAPSED_KEY } from "../hooks/useRailCollapsed";
import { SCREENS } from "../routes";

// The rail's own control. Named by what it does rather than by where it sits,
// so the test does not fix its position in the shell.
const toggle = () => screen.getByRole("button", { name: /navigation/i });

const rail = () => within(screen.getByRole("navigation", { name: /screens/i }));

const entryNames = [/operational picture/i, /hypotheses/i, /scenario control/i];

const addressOf = (id: string): string => SCREENS.find((s) => s.id === id)?.hash ?? "";

const collapse = () => fireEvent.click(toggle());

beforeEach(() => {
  window.location.hash = "";
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("collapsing the navigation rail", () => {
  it("opens expanded, and says so", () => {
    // spec: nav-003 (third decision) — expanded is the default on a first
    // visit, so nothing is hidden from someone who has never used this before,
    // and nav-001's tests keep passing unamended.
    render(<App />);

    expect(toggle()).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps all three entries, with their names, when collapsed", () => {
    // spec: nav-003 (fifth decision), FR-701 — collapsing hides labels and
    // never entries. The label goes visually; the accessible name stays, so
    // the rail reads identically to assistive technology either way.
    render(<App />);

    collapse();

    expect(rail().getAllByRole("link")).toHaveLength(3);
    for (const name of entryNames) {
      expect(rail().getByRole("link", { name })).toBeInTheDocument();
    }
    // Assert the label text itself, not only the computed name. An entry also
    // carries a tooltip while collapsed, and a tooltip supplies an accessible
    // name when nothing else does — so the loop above passes unchanged with
    // the label deleted outright. Found by mutation, after this test was
    // written; recorded as a deviation.
    for (const route of SCREENS) {
      expect(rail().getByText(route.label)).toBeInTheDocument();
    }
  });

  it("still offers a way out once collapsed", () => {
    // spec: nav-003 (first failure case) — a collapsed rail with no visible
    // control to expand it is a state the analyst cannot leave.
    render(<App />);

    collapse();

    expect(toggle()).toBeInTheDocument();
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
  });

  it("expands again from the collapsed state", () => {
    // spec: nav-003 — the control is a toggle, not a one-way door.
    render(<App />);

    collapse();
    fireEvent.click(toggle());

    expect(toggle()).toHaveAttribute("aria-expanded", "true");
    expect(rail().getByRole("link", { name: /scenario control/i })).toBeInTheDocument();
  });

  it("still marks the current page when collapsed", () => {
    // spec: nav-003 (first decision) — the whole argument for an icon rail
    // over a hidden one is that it keeps saying which screen you are on.
    render(<App />);

    collapse();

    const current = rail()
      .getAllByRole("link")
      .filter((entry) => entry.getAttribute("aria-current") === "page");

    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAccessibleName(/operational picture/i);
  });

  it("offers the toggle as a button rather than a link", () => {
    // spec: nav-003 (fourth decision) — nav-001's entries are anchors because
    // they have addresses. This one goes nowhere, so a link would be the
    // mirror image of the error nav-001 avoided: the rail would then hold four
    // links, one of which navigates to nothing.
    render(<App />);

    expect(rail().getAllByRole("link")).toHaveLength(3);
    expect(toggle().tagName).toBe("BUTTON");
  });

  it("remembers the choice across a reload", () => {
    // spec: nav-003 (second decision) — a preference that is forgotten every
    // visit is not a preference. Unmounting and rendering again is what a
    // reload looks like from in here.
    const first = render(<App />);
    collapse();
    first.unmount();

    render(<App />);

    expect(toggle()).toHaveAttribute("aria-expanded", "false");
  });

  it("opens expanded when the stored preference is corrupt", () => {
    // spec: nav-003 (fourth failure case) — storage holds whatever was last
    // written to it, including by an older version of this app. An unreadable
    // value resolves to expanded rather than blanking the rail.
    window.localStorage.setItem(RAIL_COLLAPSED_KEY, "banana");

    render(<App />);

    expect(toggle()).toHaveAttribute("aria-expanded", "true");
    expect(rail().getAllByRole("link")).toHaveLength(3);
  });

  it("opens expanded when storage cannot be read at all", () => {
    // spec: nav-003 (second decision) — reading storage throws outright in a
    // private window with site data blocked. The rail degrades to the state
    // that shows more rather than less, and does not take the app down.
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("access denied");
    });

    render(<App />);

    expect(toggle()).toHaveAttribute("aria-expanded", "true");
    expect(rail().getAllByRole("link")).toHaveLength(3);
  });

  it("keeps the preference out of the address", () => {
    // spec: nav-003 (fifth failure case) — the hash says where you are. Rail
    // width is not a location, and in the hash it would give one screen two
    // addresses and make a shared link carry someone else's chrome.
    window.location.hash = addressOf("scenario-control");
    render(<App />);

    collapse();

    expect(window.location.hash).toBe(addressOf("scenario-control"));
  });

  it("does not change which screen is shown", () => {
    // spec: nav-003 (eighth failure case) — collapsing is a change of chrome,
    // not of destination.
    window.location.hash = addressOf("scenario-control");
    render(<App />);

    collapse();

    expect(screen.getByRole("table", { name: /recent runs/i })).toBeInTheDocument();
  });

  it("stays collapsed when the analyst moves to another screen", async () => {
    // spec: nav-003 — the preference belongs to the person, not to the screen.
    render(<App />);
    collapse();

    fireEvent.click(rail().getByRole("link", { name: /hypotheses/i }));

    expect(await screen.findByText(/not built yet/i)).toBeInTheDocument();
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
  });
});
