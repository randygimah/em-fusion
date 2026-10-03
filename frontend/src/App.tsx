import { useState } from "react";
import { EmNavRail } from "./components/em/EmNavRail";
import { useCurrentScreen } from "./hooks/useCurrentScreen";
import { useRailCollapsed } from "./hooks/useRailCollapsed";
import { useScenarioControl } from "./hooks/useScenarioControl";
import { useOperationalPicture } from "./hooks/useOperationalPicture";
import { useSelectableHours } from "./hooks/useSelectableHours";
import { SCREENS } from "./routes";
import HypothesesScreen from "./screens/hypotheses";
import OperationalPictureScreen from "./screens/operationalPicture";
import ScenarioControlScreen from "./screens/scenarioControl";

// The seam, and the only place that knows where a screen's data comes from
// (spec: api-003). Both screens fetch; no screen imports a mock itself.
//
// It is also where api-011 found a defect worth recording: this destructuring
// dropped the scenario feed's refusal, so a start the backend rejected changed
// nothing on screen at all. Every value a feed exposes has to arrive somewhere,
// or the seam is where a capability goes to be silently discarded.
//
// The hook lives in here rather than in App so that it mounts and unmounts
// with the screen that needs it: left above the switch it would poll every
// five seconds while the analyst is looking at something else (nav-001).
const OperationalPictureRoute = () => {
  // Which hour is pinned, as component state and deliberately not in the URL
  // hash (spec: op-009). A pinned hour in the hash would survive a reload and
  // be shareable, which is worth having — but screenFromHash resolves a bare
  // screen id today, so a parameterised hash is nav-001's machinery and its own
  // item, with its own failure case for an unrecognised run.
  const [pinnedRun, setPinnedRun] = useState<number | null>(null);
  const hours = useSelectableHours();
  const { picture, degraded } = useOperationalPicture(pinnedRun);

  return (
    <OperationalPictureScreen
      degraded={degraded}
      hours={hours}
      onFollowNewest={() => setPinnedRun(null)}
      onSelectHour={(runId) => setPinnedRun(Number.isNaN(runId) ? null : runId)}
      operationalPicture={picture}
      pinnedRun={pinnedRun}
    />
  );
};

// Same reasoning as the picture's route above: the poll belongs to the screen
// that needs it, so it stops when the analyst is looking at something else
// (nav-001). Reset and replay stay unwired — api-006 deferred reset, and a
// single-run replay is not a request the start endpoint can make, since a
// batch is between 20 and 30 runs (spec: api-010).
const ScenarioControlRoute = () => {
  const { control, degraded, accepted, refusal, start } = useScenarioControl();

  return (
    <ScenarioControlScreen
      accepted={accepted}
      control={control}
      degraded={degraded}
      onStart={start}
      refusal={refusal}
    />
  );
};

const App = () => {
  const current = useCurrentScreen();
  const [railCollapsed, toggleRail] = useRailCollapsed();

  return (
    <div className="flex min-h-screen bg-[#0b0e15]">
      <EmNavRail
        collapsed={railCollapsed}
        currentId={current.id}
        onToggle={toggleRail}
        screens={SCREENS}
      />
      <div className="min-w-0 flex-1">
        {current.id === "operational-picture" && <OperationalPictureRoute />}
        {current.id === "hypotheses" && <HypothesesScreen />}
        {current.id === "scenario-control" && <ScenarioControlRoute />}
      </div>
    </div>
  );
};

export default App;
