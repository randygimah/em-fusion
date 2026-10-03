import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import OperationalPictureScreen from "../screens/operationalPicture";
import { SCREENS } from "../routes";
import operationalPictureMock from "../mocks/operationalPictureMock";
import type { OperationalPicture } from "../types/operationalPicture";

// spec: op-001 — the two claims the one badge was making, separated.
//
// (A) THIS SYSTEM IS NOT LIVE. True on every screen, whatever is loaded, and
// needs no input of any kind — so it lives in the rail and is asserted against
// a dead backend, an empty store and a collapsed rail. A badge with nothing to
// read has nothing that can be absent, which is a stronger form of
// "unconditional" than the item originally asked for.
//
// (B) THIS HOUR IS MADE OF synthetic RF and replayed tracks. True only of the
// hour on screen, changes per hour, and is what the bare word `mixed` was
// trying to say.
//
// The requirement behind (A) says a badge on EVERY screen, and until this item
// no screen carried one: two said nothing at all and the picture printed a
// token. That is why the standing badge is tested through App at each route
// rather than on a component in isolation.

const STANDING = /synthetic\s*&\s*replayed data/i;
const COLLAPSED = /not live/i;

const picture = (dataMode: string): OperationalPicture => ({
  ...operationalPictureMock,
  scenario: { id: "207", name: "Run 207", dataMode },
  hypotheses: [],
  rfSensors: [],
  timelineEvents: [],
  detectionSummary: null,
  aircraftTracks: [],
});

const ok = (payload: unknown) => ({ ok: true, status: 200, json: async () => payload }) as Response;

const healthy = { status: "healthy", schema: "at-head", expected: "0009", found: "0009", detail: "ok" };

let fetchMock: ReturnType<typeof vi.fn>;

const route = (input: RequestInfo | URL): Response => {
  const url = String(input);
  if (url.includes("/health")) return ok(healthy);
  if (url.includes("/hours")) return ok([]);
  if (url.includes("/scenario/runs")) return ok([]);
  return ok(picture("mixed"));
};

beforeEach(() => {
  window.location.hash = "";
  fetchMock = vi.fn((input: RequestInfo | URL) => Promise.resolve(route(input)));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.location.hash = "";
});

const rail = () => screen.getByRole("navigation", { name: /screens/i });

describe("the standing badge", () => {
  it.each(SCREENS.map((s) => [s.label, s.hash] as const))(
    "is on the %s screen",
    (_label, hash) => {
      window.location.hash = hash;
      render(<App />);

      expect(within(rail()).getByText(STANDING)).toBeInTheDocument();
    },
  );

  it("is in the rail rather than on one screen, so it needs no payload", () => {
    // The rail is the only component on all three screens. Putting the badge
    // anywhere else means either two screens without one, or the picture's
    // five-second poll mounted on screens that do not need it — which the
    // routing deliberately avoided.
    render(<App />);

    expect(within(rail()).getByText(STANDING)).toBeInTheDocument();
  });

  it("is present before any response arrives", () => {
    render(<App />);

    expect(within(rail()).getByText(STANDING)).toBeInTheDocument();
  });

  it("is present when every request fails", async () => {
    // The named failure case: a badge derived from a payload is a badge a
    // backend failure can remove.
    fetchMock.mockRejectedValue(new Error("network down"));
    render(<App />);

    expect(await within(rail()).findByText(STANDING)).toBeInTheDocument();
  });

  it("is present when the store holds nothing", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) =>
      Promise.resolve(
        String(input).includes("/health")
          ? ok(healthy)
          : ok(String(input).includes("/hours") ? [] : { ...picture("unknown"), scenario: null }),
      ),
    );
    render(<App />);

    expect(await within(rail()).findByText(STANDING)).toBeInTheDocument();
  });

  it("survives the rail collapsing, reading the claim rather than an abbreviation", () => {
    // The item requires a badge that cannot be dismissed or collapsed, and the
    // 56px rail makes that a real constraint. "NOT LIVE" is the claim itself;
    // an abbreviation of the words would be cryptic and the claim is the thing
    // that must not be lost.
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /collapse navigation/i }));

    expect(within(rail()).getByText(COLLAPSED)).toBeInTheDocument();
  });

  it("keeps the full wording as its accessible name at either width", () => {
    render(<App />);
    const expanded = within(rail()).getByRole("status", { name: STANDING });
    expect(expanded).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /collapse navigation/i }));

    expect(within(rail()).getByRole("status", { name: STANDING })).toBeInTheDocument();
  });

  it("does not become a fourth nav entry", () => {
    // spec: nav-001, FR-701 — the rail is exactly three entries and the badge
    // is chrome, not a destination.
    render(<App />);

    expect(within(rail()).getAllByRole("link")).toHaveLength(SCREENS.length);
  });
});

describe("what this hour is made of", () => {
  it.each([
    ["mixed", /synthetic rf \+ replayed tracks/i],
    ["synthetic", /^synthetic rf$/i],
    ["replayed", /^replayed tracks$/i],
  ] as const)("renders %s in words", (dataMode, expected) => {
    render(<OperationalPictureScreen operationalPicture={picture(dataMode)} />);

    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("renders an hour with no observations as what that means", () => {
    // `unknown` is produced by a run with nothing stored against it, not by any
    // uncertainty, so rendering it as "unknown" states the wrong thing.
    render(<OperationalPictureScreen operationalPicture={picture("unknown")} />);

    expect(screen.getByText(/no observations in this hour/i)).toBeInTheDocument();
  });

  it.each(["mixed", "synthetic", "replayed", "unknown"])(
    "never renders the payload's token verbatim for %s",
    (dataMode) => {
      // The defect this item is fixing: the screen printed the token.
      render(<OperationalPictureScreen operationalPicture={picture(dataMode)} />);

      expect(screen.queryByText(dataMode)).not.toBeInTheDocument();
    },
  );

  it("is labelled, so the value is not a bare word", () => {
    render(<OperationalPictureScreen operationalPicture={picture("mixed")} />);

    expect(screen.getByText(/^data$/i)).toBeInTheDocument();
  });

  it("renders nothing about the data mode when there is no scenario", () => {
    render(
      <OperationalPictureScreen
        operationalPicture={{ ...picture("mixed"), scenario: null }}
      />,
    );

    expect(screen.queryByText(/^data$/i)).not.toBeInTheDocument();
  });

  it("no longer renders a scenario health value", () => {
    // spec: api-014 — the field is gone from the contract, and the screen used
    // to print it as a second bare word reading `unknown` forever.
    render(<OperationalPictureScreen operationalPicture={picture("mixed")} />);

    expect(screen.queryByText(/^unknown$/i)).not.toBeInTheDocument();
  });
});
