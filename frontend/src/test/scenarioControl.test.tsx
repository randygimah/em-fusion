import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import scenarioControlMock from "../mocks/scenarioControlMock";
import ScenarioControlScreen from "../screens/scenarioControl";
import type { ScenarioConfiguration, ScenarioControl, ScenarioRunRecord } from "../types/scenarioControl";

// The handlers are optional on purpose: `api-006` does not exist, so the screen
// has to render honestly with nothing behind its controls (spec: scn-004,
// second decision). Passing them explicitly is what a test does to say "assume
// the endpoint is there".
type Handlers = {
  onStart?: (configuration: ScenarioConfiguration) => void;
  onReset?: () => void;
  onReplay?: (run: ScenarioRunRecord) => void;
};

const renderScreen = ({ control = scenarioControlMock, ...handlers }: { control?: ScenarioControl } & Handlers = {}) =>
  render(
    <ScenarioControlScreen
      control={control}
      {...handlers}
    />,
  );

const wired = () => {
  const onStart = vi.fn();
  const onReset = vi.fn();
  const onReplay = vi.fn();
  renderScreen({ onStart, onReset, onReplay });
  return { onStart, onReset, onReplay };
};

const field = (label: string | RegExp): HTMLInputElement => screen.getByLabelText(label) as HTMLInputElement;

const setField = (label: string | RegExp, value: string) => fireEvent.change(field(label), { target: { value } });

const startButton = () => screen.getByRole("button", { name: /^start/i });

const table = () => within(screen.getByRole("table", { name: /recent runs/i }));

// The run that is deliberately unfinished in the mock, and the one that is not.
const [incomplete, completed] = scenarioControlMock.runs;

describe("ScenarioControlScreen", () => {
  // ------------------------------------------------------------- the library

  it("offers exactly the five scenario types and no sixth", () => {
    // spec: scn-004, FR-202 — the closed set is the generator's, and a screen
    // offering a type it cannot generate is a run that cannot be started.
    renderScreen();

    const entries = within(screen.getByRole("region", { name: /scenario library/i })).getAllByRole("button");

    expect(entries).toHaveLength(5);
    for (const entry of scenarioControlMock.library) {
      expect(screen.getByRole("button", { name: new RegExp(entry.name, "i") })).toBeInTheDocument();
    }
  });

  it("configures the type that was chosen from the library", () => {
    // spec: scn-004 — choosing from the library and starting must agree; a
    // selection the start payload ignores is a screen that lies about what it
    // ran.
    const { onStart } = wired();

    fireEvent.click(screen.getByRole("button", { name: /data-source coverage gap/i }));
    fireEvent.click(startButton());

    expect(onStart).toHaveBeenCalledWith(expect.objectContaining({ scenarioType: "aircraft-coverage-gap" }));
  });

  // ------------------------------------------------------- the configuration

  it("shows a seed field that can be edited", () => {
    // spec: scn-004, FR-201, US-E1 — the item's own constraint. This screen is
    // the visible face of the evaluation harness, so the seed is not something
    // it hides and generates behind the analyst's back.
    renderScreen();

    setField(/base seed/i, "20220627");

    expect(field(/base seed/i).value).toBe("20220627");
  });

  it("exposes every dial the batch entrypoint accepts", () => {
    // spec: scn-004 (third decision) — the frontend half. The backend half is
    // the parity test, which compares these against the parser rather than
    // against this list.
    renderScreen();

    for (const label of [
      /base seed/i,
      /runs in batch/i,
      /run duration/i,
      /incident offset/i,
      /incident duration/i,
      /zone radius/i,
      /noise elevation/i,
      /spectral extent/i,
    ]) {
      expect(field(label)).toBeInTheDocument();
    }
  });

  it("offers no dial the generator does not have", () => {
    // spec: scn-004 (third decision), scn-001 — the design mockup shows noise
    // amplitude, affected sensor count and gap duration. A control that
    // changes nothing is the same defect as a seed that changes nothing, which
    // is scn-001's fourth failure case.
    //
    // Green against the stub, which renders no labels at all, so it proves
    // nothing until the form exists. Mutation-proved afterwards instead: add
    // the mockup's noise-amplitude field and this is what goes red.
    renderScreen();

    for (const absent of [/noise amplitude/i, /affected sensor count/i, /gap duration/i]) {
      expect(screen.queryByLabelText(absent)).not.toBeInTheDocument();
    }
  });

  it("renders a seed as the integer the run record holds, never as hex", () => {
    // spec: scn-004 (fourth decision) — the mockup shows 0xA4F2. A seed exists
    // to be pasted back into a command or re-sent by replay, and a second
    // representation is a conversion to get wrong.
    renderScreen();

    expect(table().getByText(String(completed.seed))).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/0x[0-9a-f]+/i);
  });

  it("refuses a seed the run record cannot hold", () => {
    // spec: scn-004 (fourth decision), scn-001 — scenario_runs.seed is a
    // 32-bit signed integer, so 2**31 is a run that cannot be reproduced from
    // its own row. Refused here rather than discovered by the batch.
    const { onStart } = wired();

    setField(/base seed/i, String(2 ** 31));
    fireEvent.click(startButton());

    expect(onStart).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/2147483647/);
  });

  it("refuses a batch outside twenty to thirty runs", () => {
    // spec: scn-004, scn-003, FR-205 — fewer than twenty cannot carry a
    // per-type rate worth quoting, and the batch itself raises on both bounds.
    const { onStart } = wired();

    setField(/runs in batch/i, "5");
    fireEvent.click(startButton());

    expect(onStart).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/20/);
  });

  // ----------------------------------------------------------- the controls

  it("disables the run controls and says why when nothing can start a run", () => {
    // spec: scn-004 (second decision), NFR-204 — api-006 does not exist. A
    // button that posts nowhere claims a capability the system does not have.
    renderScreen();

    expect(startButton()).toBeDisabled();
    expect(screen.getByRole("button", { name: /^reset/i })).toBeDisabled();
    expect(screen.getByRole("note")).toHaveTextContent(/command line/i);
  });

  it("keeps the disabled controls on screen rather than hiding them", () => {
    // spec: scn-004 (second decision), NFR-204 — a hidden control is an
    // unbuilt capability the screen conceals; a disabled one is an unbuilt
    // capability the screen admits to.
    renderScreen();

    expect(startButton()).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reset/i })).toBeInTheDocument();
  });

  it("starts a run with the configured values", () => {
    // spec: scn-004, scn-003 — the defaults are the batch entrypoint's own:
    // twenty runs of fifteen simulated minutes, an incident two minutes in
    // lasting five, 60 km, 8 dB, narrowband.
    const { onStart } = wired();

    setField(/base seed/i, "20220627");
    fireEvent.click(startButton());

    expect(onStart).toHaveBeenCalledTimes(1);
    expect(onStart).toHaveBeenCalledWith({
      scenarioType: "normal-baseline",
      baseSeed: 20220627,
      runs: 20,
      durationSeconds: 900,
      incidentOffsetS: 120,
      incidentDurationS: 300,
      radiusKm: 60,
      elevationDb: 8,
      spectralExtent: "narrowband",
    });
  });

  it("resets through the handler it was given", () => {
    // spec: scn-004, FR-714 — reset is one of the run controls, and the test
    // stage wrote assertions for its disabled state and none for its use.
    //
    // **Written after the implementation.** A deviation from this project's
    // order, recorded here rather than tidied away: the frontend measures no
    // coverage, so nothing reported that this button's handler was never
    // called by a test. See docs/handoff.md.
    const { onReset } = wired();

    fireEvent.click(screen.getByRole("button", { name: /^reset/i }));

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("carries the spectral extent it was told to use", () => {
    // spec: scn-004, scn-002 — extent is a parameter of the interference
    // types rather than a sixth type, which only means anything if a campaign
    // can actually turn the dial.
    //
    // **Written after the implementation**, for the reason above: no test
    // changed this control, so nothing proved the value reached the payload.
    const { onStart } = wired();

    fireEvent.change(field(/spectral extent/i), { target: { value: "broadband" } });
    fireEvent.click(startButton());

    expect(onStart).toHaveBeenCalledWith(expect.objectContaining({ spectralExtent: "broadband" }));
  });

  it("names a run whose type the library does not list", () => {
    // spec: scn-004 — a run recorded by an older generator can carry a type
    // this library no longer names, and a blank cell would hide the run
    // rather than the gap.
    //
    // **Written after the implementation**, for the reason above.
    renderScreen({ control: { library: [], runs: scenarioControlMock.runs } });

    expect(table().getByText("gnss-degradation")).toBeInTheDocument();
  });

  it("offers no pause control", () => {
    // spec: scn-004 (seventh decision) — FR-714 lists pause; generation has
    // nothing to pause, since a batch is a loop of whole runs each committing
    // atomically. Pause belongs to FR-717's playback transport (op-008). A
    // dead control here would be the screen claiming a lifecycle nothing has.
    //
    // Green against the stub for the same reason as the dials above, and
    // mutation-proved the same way.
    renderScreen();

    expect(screen.queryByRole("button", { name: /pause/i })).not.toBeInTheDocument();
  });

  // -------------------------------------------------------- the seed's round trip

  it("starts without a seed rather than inventing one", () => {
    // spec: scn-004 (fifth decision), scn-001 — the seed is recorded including
    // when it was generated rather than supplied, and api-006 echoes it back.
    // A seed the screen invented would be one the run record never saw.
    const { onStart } = wired();

    fireEvent.click(startButton());

    expect(onStart).toHaveBeenCalledWith(expect.objectContaining({ baseSeed: null }));
  });

  it("shows the seed of a run that was started without one", () => {
    // spec: scn-004 — the item's stated failure case: starting with no seed
    // entered and no seed shown afterwards is a run nobody can repeat.
    const started = { ...completed, id: 49, seed: 1631659769 };
    renderScreen({ control: { ...scenarioControlMock, runs: [started, ...scenarioControlMock.runs] } });

    expect(table().getByText("1631659769")).toBeInTheDocument();
  });

  // ------------------------------------------------------------------ replay

  it("replays a listed run at that run's recorded seed and parameters", () => {
    // spec: scn-004 (sixth decision) — not the form's current values under the
    // row's seed, which is reproducible in name only. RunSpec.from_record is
    // the server-side half of the same guarantee.
    const { onReplay } = wired();

    setField(/base seed/i, "1");
    setField(/zone radius/i, "75");
    fireEvent.click(within(table().getByRole("row", { name: new RegExp(String(completed.seed)) })).getByRole("button", { name: /replay/i }));

    expect(onReplay).toHaveBeenCalledWith(completed);
  });

  it("loads a replayed run's recorded values into the configuration", () => {
    // spec: scn-004 (sixth decision) — what is started has to be what is
    // listed, and the analyst has to be able to see that it is.
    wired();

    setField(/base seed/i, "1");
    setField(/zone radius/i, "75");
    fireEvent.click(within(table().getByRole("row", { name: new RegExp(String(completed.seed)) })).getByRole("button", { name: /replay/i }));

    expect(field(/base seed/i).value).toBe(String(completed.seed));
    expect(field(/zone radius/i).value).toBe(String(completed.parameters.radius_km));
    expect(field(/incident offset/i).value).toBe(String(completed.parameters.start_offset_s));
  });

  // ------------------------------------------------- the table and the status

  it("lists each run with its type, seed and outcome", () => {
    // spec: scn-004, FR-714 — and the scenario type is legitimately here:
    // api-009 keeps the answer key off observations, detector inputs, bundles
    // and the analyst picture. This screen is the harness's own face.
    renderScreen();

    const row = table().getByRole("row", { name: new RegExp(String(completed.seed)) });

    expect(within(row).getByText(/gnss signal degradation/i)).toBeInTheDocument();
    expect(within(row).getByText(String(completed.seed))).toBeInTheDocument();
    expect(within(row).getByText(/complete/i)).toBeInTheDocument();
  });

  it("shows a run with no completion stamp as unfinished rather than complete", () => {
    // spec: scn-004, db-007 — absence is the informative state. The row cannot
    // tell a run still going from one that died, and the screen must not
    // choose one of them on its behalf.
    renderScreen();

    const row = table().getByRole("row", { name: new RegExp(String(incomplete.seed)) });

    expect(within(row).getByText(/incomplete/i)).toBeInTheDocument();
    expect(within(row).queryByText(/^complete$/i)).not.toBeInTheDocument();
  });

  it("reports the run status from the most recent run rather than inventing one", () => {
    // spec: scn-004, db-007 — with no runs recorded there is nothing to
    // report, and idle is the honest reading. The alternative, a green
    // "ready", is a claim about a system that has never been asked to do
    // anything.
    const { unmount } = renderScreen({ control: { ...scenarioControlMock, runs: [] } });

    expect(screen.getByRole("status")).toHaveTextContent(/idle/i);

    unmount();
    renderScreen();

    expect(screen.getByRole("status")).toHaveTextContent(/incomplete/i);
  });
});
