import { useCallback, useState } from "react";
import { EmDataModeBadge } from "./components/em/EmDataModeBadge";
import { EmNavRail } from "./components/em/EmNavRail";
import { EmSystemStatus } from "./components/em/EmSystemStatus";
import { useCurrentScreen } from "./hooks/useCurrentScreen";
import { useRailCollapsed } from "./hooks/useRailCollapsed";
import { useScenarioControl } from "./hooks/useScenarioControl";
import { useEvidenceAccount } from "./hooks/useEvidenceAccount";
import { useOperationalPicture } from "./hooks/useOperationalPicture";
import { useSelectableHours } from "./hooks/useSelectableHours";
import { useSystemHealth } from "./hooks/useSystemHealth";
import { fetchHypotheses, fetchHypothesis, fetchOperationalPicture, fetchReceiverStates, fetchTracks } from "./lib/api";
import { DEFAULT_VIEW } from "./lib/viewVocabulary";
import { SCREENS } from "./routes";
import HypothesesScreen from "./screens/hypotheses";
import OperationalPictureScreen from "./screens/operationalPicture";
import ScenarioControlScreen from "./screens/scenarioControl";
import type { ViewSelection } from "./types/operationalPicture";

// The Hypotheses screen's reads (spec: hyp-001): the list, the explanation the
// address names, and the conclusion's hour unfiltered for its map. Module-level,
// so they are stable across renders and never refetch for that reason.
const loadHypothesisList = () => fetchHypotheses();
const loadHypothesis = (id: number) => fetchHypothesis(id);
const loadConclusionHour = (runId: number) => fetchOperationalPicture("", runId, "all");

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
  // The view, as component state for the same reason (spec: op-007): it lasts
  // as long as the screen, across polls and hours, and every visit starts at
  // Anomalous only (US-A1) rather than on a view somebody left.
  const [view, setView] = useState<ViewSelection>(DEFAULT_VIEW);
  const hours = useSelectableHours();
  const { picture, degraded } = useOperationalPicture(pinnedRun, view);
  // Keyed on the same pinned hour as the picture, so the evidence on screen
  // always belongs to the conclusion above it (spec: op-010).
  const evidence = useEvidenceAccount(pinnedRun);
  // The drill-down tables (spec: op-005) read the endpoint the panel reads, for
  // the hour the panel names and never filtered: a view over the same data,
  // fetched when asked for and not polled.
  const loadUnfiltered = useCallback((runId: number) => fetchOperationalPicture("", runId, "all"), []);
  // Playback's spans of positions (spec: map-004, api-008), fetched as the
  // buffer needs them and never polled.
  const loadTracks = useCallback((runId: number, from: string, to: string, view: ViewSelection) => fetchTracks(runId, from, to, view), []);
  // Playback's receiver states (spec: map-007, api-018), once per opening.
  const loadReceiverStates = useCallback((runId: number) => fetchReceiverStates(runId), []);

  return (
    <OperationalPictureScreen
      degraded={degraded}
      evidence={evidence}
      hours={hours}
      loadReceiverStates={loadReceiverStates}
      loadTracks={loadTracks}
      loadUnfiltered={loadUnfiltered}
      onFollowNewest={() => setPinnedRun(null)}
      onSelectHour={(runId) => setPinnedRun(Number.isNaN(runId) ? null : runId)}
      onSelectView={setView}
      operationalPicture={picture}
      pinnedRun={pinnedRun}
      selectedView={view}
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
  // The two things in the rail footer, and they live here rather than one
  // screen down for opposite reasons. The badge is unconditional and on every
  // screen, so it must not hang off a screen's data (op-001). The status strip
  // reads the service's own health route, which is cheap and is the same on
  // every screen — unlike the picture, whose poll stays with the picture
  // (nav-001, nav-002).
  const systemHealth = useSystemHealth();

  return (
    <div className="flex min-h-screen bg-[#0b0e15]">
      <EmNavRail
        collapsed={railCollapsed}
        currentId={current.screen.id}
        footer={
          <>
            <EmDataModeBadge collapsed={railCollapsed} />
            <EmSystemStatus collapsed={railCollapsed} {...systemHealth} />
          </>
        }
        onToggle={toggleRail}
        screens={SCREENS}
      />
      <div className="min-w-0 flex-1">
        {current.screen.id === "operational-picture" && <OperationalPictureRoute />}
        {current.screen.id === "hypotheses" && (
          <HypothesesScreen
            hypothesisId={current.hypothesisId}
            loadDetail={loadHypothesis}
            loadList={loadHypothesisList}
            loadPicture={loadConclusionHour}
          />
        )}
        {current.screen.id === "scenario-control" && <ScenarioControlRoute />}
      </div>
    </div>
  );
};

export default App;
