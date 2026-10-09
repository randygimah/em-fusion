import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import operationalPictureMock from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";
import type { OperationalPicture, SelectableHour } from "../types/operationalPicture";

// spec: op-008 — the playback transport.
//
// The map shows the end of an hour; this is the control that moves a cursor
// through it, in the replayed hour's own time. The cursor is all it produces:
// map-004 reads it to place aircraft. So the properties tested here are the
// cursor's — where it starts, how fast it moves, that it stops at the edges,
// that a break does not make it leap, and that nothing in it is today's time.

// The module under test, looked up rather than imported, so its absence fails
// each test that uses it instead of the whole file at load -- which would hide
// a component test passing for the wrong reason. The backend suites' late
// import, in this toolchain's terms.
const modules = import.meta.glob<typeof import("../lib/playback")>("../lib/playback.ts", { eager: true });
const lib = () => {
  const found = modules["../lib/playback.ts"];
  if (!found) throw new Error("src/lib/playback.ts does not exist");
  return found;
};

// Run 480's window, from the hours index.
const START = Date.UTC(2022, 5, 27, 12, 36, 51);
const END = Date.UTC(2022, 5, 27, 12, 51, 51);
const WINDOW = { start: START, end: END };

const HOURS: SelectableHour[] = [
  { runId: 480, observedFrom: "2022-06-27T12:36:51+00:00", observedTo: "2022-06-27T12:51:51+00:00", examined: true },
  { runId: 207, observedFrom: "2022-06-27T12:44:12+00:00", observedTo: "2022-06-27T12:59:12+00:00", examined: true },
  { runId: 99, observedFrom: null, observedTo: null, examined: false },
];

const pictureOf = (runId: string): OperationalPicture => ({
  ...operationalPictureMock,
  scenario: { id: runId, name: `Run ${runId}`, dataMode: "mixed" },
});

const show = ({
  runId = "480",
  pinnedRun = null as number | null,
  onSelectHour = vi.fn(),
  hours = HOURS,
} = {}) => {
  const view = render(
    <OperationalPictureScreen
      hours={hours}
      onSelectHour={onSelectHour}
      operationalPicture={pictureOf(runId)}
      pinnedRun={pinnedRun}
    />,
  );
  return { ...view, onSelectHour };
};

const openPlayback = () => fireEvent.click(screen.getByRole("button", { name: /play back this hour/i }));
const bar = () => screen.getByRole("region", { name: /playback/i });
const slider = () => within(bar()).getByRole("slider", { name: /playback position/i });
const cursorOnSlider = () => Number((slider() as HTMLInputElement).value);
const mapCursor = () => within(screen.getByTestId("map-view-stub")).getByText(/^cursor:/).textContent;
const playButton = () => within(bar()).getByRole("button", { name: /^(play|pause)$/i });
const chooseSpeed = (label: string) => fireEvent.click(within(bar()).getByRole("radio", { name: label }));

// Animation frames and the clock, faked together, so a test can say "a second
// passes" and the transport sees one second of frames.
const fakeFrames = () => vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame", "Date", "performance"] });
const pass = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

afterEach(() => {
  vi.useRealTimers();
});

describe("the cursor's arithmetic", () => {
  it("moves by elapsed time multiplied by the speed", () => {
    // spec: op-008
    expect(lib().advance(START, 1000, 4, WINDOW)).toBe(START + 4000);
  });

  it("reaches the same moment whichever speed it is played at", () => {
    // spec: op-008 — the named failure case, at the cursor: speed must not
    // change which simulated moment a given amount of play reaches.
    expect(lib().advance(START, 4000, 1, WINDOW)).toBe(lib().advance(START, 1000, 4, WINDOW));
    expect(lib().advance(START, 600, 60, WINDOW)).toBe(lib().advance(START, 2250, 16, WINDOW));
  });

  it("never runs past either end of the window", () => {
    // spec: op-008
    expect(lib().advance(END - 1000, 200, 60, WINDOW)).toBe(END);
    expect(lib().advance(START - 5000, 0, 1, WINDOW)).toBe(START);
  });

  it("caps one frame's interval, so a hidden tab does not make it leap", () => {
    // spec: op-008 — the browser runs no frames in a hidden tab, and the first
    // frame back would otherwise carry the whole absence.
    expect(lib().frameInterval(1_000, 61_000)).toBe(lib().MAX_FRAME_MS);
    expect(lib().frameInterval(1_000, 1_016)).toBe(16);
    expect(lib().MAX_FRAME_MS).toBeLessThanOrEqual(250);
  });

  it("offers the four speeds", () => {
    // spec: op-008
    expect(lib().PLAYBACK_SPEEDS).toEqual([1, 4, 16, 60]);
  });
});

describe("what the transport says", () => {
  it("names the cursor as the replayed hour's UTC clock time", () => {
    // spec: op-008 — simulated time, in UTC whatever the viewer's zone.
    expect(lib().clockLabel(START + 269_000)).toBe("12:41:20 UTC");
  });

  it("names the cursor as elapsed against the window's length", () => {
    // spec: op-008
    expect(lib().elapsedLabel(START + 269_000, WINDOW)).toBe("4:29 of 15:00");
    expect(lib().elapsedLabel(START, WINDOW)).toBe("0:00 of 15:00");
  });
});

describe("opening and closing", () => {
  it("is off by default and hands the map no cursor", () => {
    // spec: op-008 — the screen opens on the end of the hour, as before.
    show();

    expect(screen.queryByRole("region", { name: /playback/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /play back this hour/i })).toBeEnabled();
    expect(mapCursor()).toBe("cursor: none");
  });

  it("opens paused at the start of the hour and hands the map the cursor", () => {
    // spec: op-008
    show();
    openPlayback();

    expect(cursorOnSlider()).toBe(START);
    expect(within(bar()).getByText("12:36:51 UTC")).toBeInTheDocument();
    expect(within(bar()).getByText("0:00 of 15:00")).toBeInTheDocument();
    expect(playButton()).toHaveAccessibleName("Play");
    expect(mapCursor()).toBe(`cursor: ${new Date(START).toISOString()}`);
  });

  it("closes back to the end of the hour", () => {
    // spec: op-008
    show();
    openPlayback();

    fireEvent.click(within(bar()).getByRole("button", { name: /close playback/i }));

    expect(screen.queryByRole("region", { name: /playback/i })).not.toBeInTheDocument();
    expect(mapCursor()).toBe("cursor: none");
  });

  it("is disabled, with a reason, for an hour with no recorded window", () => {
    // spec: op-008
    show({ runId: "99" });

    expect(screen.getByRole("button", { name: /play back this hour/i })).toBeDisabled();
    expect(screen.getByText(/no recorded window to play back/i)).toBeInTheDocument();
  });
});

describe("the hour being played", () => {
  it("is pinned when playback opens while following the newest hour", () => {
    // spec: op-008, op-009 — so a newer hour cannot move the ground under the cursor.
    const { onSelectHour } = show({ pinnedRun: null });

    openPlayback();

    expect(onSelectHour).toHaveBeenCalledWith(480);
  });

  it("is not pinned again when it already is", () => {
    // spec: op-008
    const { onSelectHour } = show({ pinnedRun: 480 });

    openPlayback();

    expect(onSelectHour).not.toHaveBeenCalled();
  });

  it("closes playback when another hour comes on screen", () => {
    // spec: op-008 — the named failure case: a different hour silently played.
    const { rerender, onSelectHour } = show({ pinnedRun: 480 });
    openPlayback();

    rerender(
      <OperationalPictureScreen
        hours={HOURS}
        onSelectHour={onSelectHour}
        operationalPicture={pictureOf("207")}
        pinnedRun={207}
      />,
    );

    expect(screen.queryByRole("region", { name: /playback/i })).not.toBeInTheDocument();
    expect(mapCursor()).toBe("cursor: none");
  });
});

describe("playing", () => {
  it("advances the cursor by elapsed time multiplied by the chosen speed", () => {
    // spec: op-008
    fakeFrames();
    show();
    openPlayback();
    chooseSpeed("4×");

    fireEvent.click(playButton());
    pass(10_000);

    // Forty simulated seconds, less at most a frame or two at the start.
    const moved = cursorOnSlider() - START;
    expect(moved).toBeGreaterThan(39_800);
    expect(moved).toBeLessThanOrEqual(40_000);
    expect(playButton()).toHaveAccessibleName("Pause");
  });

  it("holds the cursor when paused rather than resetting it", () => {
    // spec: op-008
    fakeFrames();
    show();
    openPlayback();
    fireEvent.click(playButton());
    pass(5_000);

    fireEvent.click(playButton());
    const held = cursorOnSlider();
    pass(5_000);

    expect(held).toBeGreaterThan(START);
    expect(cursorOnSlider()).toBe(held);
    expect(playButton()).toHaveAccessibleName("Play");
  });

  it("stops at the end of the hour, and plays from the start again", () => {
    // spec: op-008 — never past the end.
    fakeFrames();
    show();
    openPlayback();
    chooseSpeed("60×");
    fireEvent.click(playButton());

    pass(20_000);

    expect(cursorOnSlider()).toBe(END);
    expect(playButton()).toHaveAccessibleName("Play");
    expect(within(bar()).getByText("15:00 of 15:00")).toBeInTheDocument();

    fireEvent.click(playButton());
    expect(cursorOnSlider()).toBe(START);
  });

  it("offers the speeds and marks the chosen one", () => {
    // spec: op-008
    show();
    openPlayback();

    const group = within(bar()).getByRole("radiogroup", { name: /speed/i });
    expect(
      within(group)
        .getAllByRole("radio")
        .map((radio) => radio.textContent),
    ).toEqual(["1×", "4×", "16×", "60×"]);
    expect(within(group).getByRole("radio", { name: "1×" })).toBeChecked();
    chooseSpeed("16×");
    expect(within(group).getByRole("radio", { name: "16×" })).toBeChecked();
  });

  it("never shows or uses today's time", () => {
    // spec: op-008, anom-009 — the wall clock is 2026; the hour is 2022.
    fakeFrames();
    vi.setSystemTime(new Date("2026-10-09T09:15:00Z"));
    show();
    openPlayback();

    expect(within(bar()).getByText("12:36:51 UTC")).toBeInTheDocument();
    expect(within(bar()).queryByText(/09:15/)).not.toBeInTheDocument();
    expect(cursorOnSlider()).toBe(START);
  });
});

describe("scrubbing", () => {
  it("spans exactly the window, in steps of the reporting cadence", () => {
    // spec: op-008 — arrow keys step 10 s; Home and End reach the edges.
    show();
    openPlayback();

    expect(slider()).toHaveAttribute("min", String(START));
    expect(slider()).toHaveAttribute("max", String(END));
    expect(slider()).toHaveAttribute("step", "10000");
  });

  it("tells assistive technology the time, not a number", () => {
    // spec: op-008
    show();
    openPlayback();

    expect(slider()).toHaveAttribute("aria-valuetext", "12:36:51 UTC");
  });

  it("moves the cursor to any point, backwards as well as forwards", () => {
    // spec: op-008
    show();
    openPlayback();

    fireEvent.change(slider(), { target: { value: String(START + 600_000) } });
    expect(cursorOnSlider()).toBe(START + 600_000);
    expect(within(bar()).getByText("10:00 of 15:00")).toBeInTheDocument();
    expect(mapCursor()).toBe(`cursor: ${new Date(START + 600_000).toISOString()}`);

    fireEvent.change(slider(), { target: { value: String(START + 60_000) } });
    expect(cursorOnSlider()).toBe(START + 60_000);
  });
});
