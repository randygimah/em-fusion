import { EmNavRail } from "./components/em/EmNavRail";
import { useCurrentScreen } from "./hooks/useCurrentScreen";
import { useRailCollapsed } from "./hooks/useRailCollapsed";
import { useScenarioControl } from "./hooks/useScenarioControl";
import { useOperationalPicture } from "./hooks/useOperationalPicture";
import { SCREENS } from "./routes";
import HypothesesScreen from "./screens/hypotheses";
import OperationalPictureScreen from "./screens/operationalPicture";
import ScenarioControlScreen from "./screens/scenarioControl";

// The seam, and the only place that knows where a screen's data comes from
// (spec: api-003). The picture is fetched; the scenario control fixture is
// imported, because api-006 does not exist. No screen imports a mock itself.
//
// The hook lives in here rather than in App so that it mounts and unmounts
// with the screen that needs it: left above the switch it would poll every
// five seconds while the analyst is looking at something else (nav-001).
const OperationalPictureRoute = () => {
  const { picture, degraded } = useOperationalPicture();

  return (
    <OperationalPictureScreen
      operationalPicture={picture}
      degraded={degraded}
    />
  );
};

// Same reasoning as the picture's route above: the poll belongs to the screen
// that needs it, so it stops when the analyst is looking at something else
// (nav-001). Reset and replay stay unwired — api-006 deferred reset, and a
// single-run replay is not a request the start endpoint can make, since a
// batch is between 20 and 30 runs (spec: api-010).
const ScenarioControlRoute = () => {
  const { control, degraded, accepted, start } = useScenarioControl();

  return (
    <ScenarioControlScreen
      accepted={accepted}
      control={control}
      degraded={degraded}
      onStart={start}
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
