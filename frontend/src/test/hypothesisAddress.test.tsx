import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import * as routes from "../routes";
import type { ScreenRoute } from "../routes";

// spec: nav-004 — each explanation's own address, '#/hypotheses/<id>', parsed
// and built in routes.ts so the cards and the parser cannot disagree.

type Route = { screen: ScreenRoute; hypothesisId: number | null };
const api = routes as unknown as {
  routeFromHash: (hash: string) => Route;
  hypothesisHash: (id: number) => string;
};

const rail = () => within(screen.getByRole("navigation", { name: /screens/i }));

beforeEach(() => {
  window.location.hash = "";
});

describe("an explanation's address (nav-004)", () => {
  it("is built by one function in routes.ts", () => {
    expect(api.hypothesisHash(41)).toBe("#/hypotheses/41");
  });

  it("resolves to the Hypotheses screen with that explanation", () => {
    const route = api.routeFromHash(api.hypothesisHash(41));

    expect(route.screen.id).toBe("hypotheses");
    expect(route.hypothesisId).toBe(41);
  });

  it("resolves the bare screen address with no explanation", () => {
    const route = api.routeFromHash("#/hypotheses");

    expect(route.screen.id).toBe("hypotheses");
    expect(route.hypothesisId).toBeNull();
  });

  it.each([
    "#/hypotheses/abc",
    "#/hypotheses/0",
    "#/hypotheses/-3",
    "#/hypotheses/041",
    "#/hypotheses/41/extra",
    "#/hypotheses/4.5",
  ])("resolves %s to the Hypotheses screen with no explanation, never a guessed one", (hash) => {
    const route = api.routeFromHash(hash);

    expect(route.screen.id).toBe("hypotheses");
    expect(route.hypothesisId).toBeNull();
  });

  it("keeps an unrecognised address on the Operational Picture", () => {
    const route = api.routeFromHash("#/nowhere");

    expect(route.screen.id).toBe("operational-picture");
    expect(route.hypothesisId).toBeNull();
  });

  it("is not read as an unrecognised address by the screen lookup", () => {
    // '#/hypotheses/41' resolved to the Operational Picture before this item.
    expect(routes.screenFromHash("#/hypotheses/41").id).toBe("hypotheses");
  });

  it("opens the Hypotheses screen, marked current in the rail, naming the explanation", () => {
    window.location.hash = "#/hypotheses/41";
    render(<App />);

    expect(
      rail()
        .getByRole("link", { name: /hypotheses/i })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(screen.getByRole("heading", { level: 1, name: /hypotheses/i })).toBeInTheDocument();
    expect(screen.getByText(/explanation 41/i)).toBeInTheDocument();
    // A parameter of one of the three entries, not a fourth (FR-701).
    expect(rail().getAllByRole("link")).toHaveLength(3);
    expect(routes.SCREENS).toHaveLength(3);
  });
});
