import { EmEvidencePanel } from "../components/em/EmEvidencePanel";
import { EmExceptionPanel } from "../components/em/EmExceptionPanel";
import { EmLevel } from "../components/em/EmLevel";
import { MapView } from "../components/map/MapView";
import { findingLabel } from "../lib/detectionVocabulary";
import { showingSentence, VIEW_OPTIONS } from "../lib/viewVocabulary";
import type { EvidenceView } from "../types/evidence";
import type {
  OperationalPicture as OperationalPictureData,
  SelectableHour,
  ViewSelection,
} from "../types/operationalPicture";

// One hour as the selector names it. spec: op-009.
//
// The run number and the replayed window, and nothing else — there is no
// scenario type to render because the payload has no field for one, which is
// the guarantee being structural rather than a rule about this function.
//
// An hour whose record holds no window is labelled by its number alone. The
// alternative is the named failure case: the run's own timestamps are when the
// generator ran, which for this corpus is four years after the hour it replays.
// What this hour is made of, in words. spec: op-001.
//
// The other half of the badge that used to be one thing: the standing claim
// that the system is not live is in the nav rail and needs no data, and this is
// the per-hour claim, which changes with the hour and is only true of the screen
// showing it.
//
// `unknown` is rendered as what it means rather than as the word. The payload
// produces it for a run with no observations stored against it — not for any
// uncertainty — so "unknown" would state the wrong thing, and this is the same
// distinction api-012 drew between a run nobody examined and a run found clean.
const DATA_MODE: Record<string, string> = {
  mixed: "Synthetic RF + replayed tracks",
  synthetic: "Synthetic RF",
  replayed: "Replayed tracks",
  unknown: "No observations in this hour",
};

// A mode the payload has never produced is named rather than printed, so an
// unfamiliar token cannot reach the screen as a bare word — which is the defect
// this item exists to fix, and reprinting it under a new name would be the same
// defect wearing a label.
const dataModeLabel = (mode: string): string => DATA_MODE[mode] ?? "Unrecognised data mode";

const hourLabel = (hour: SelectableHour): string => {
  if (hour.observedFrom === null) return `Run ${hour.runId}`;
  const from = new Date(hour.observedFrom);
  const to = hour.observedTo === null ? null : new Date(hour.observedTo);
  const day = from.toISOString().slice(0, 10);
  const clock = (at: Date) => at.toISOString().slice(11, 16);
  const span = to === null ? clock(from) : `${clock(from)}–${clock(to)}`;
  return `Run ${hour.runId} · ${day} ${span}`;
};

interface Props {
  operationalPicture: OperationalPictureData; //screen accepts data as a prop, which is of type OperationalPictureData
  // spec: api-003 — true while the picture on screen is not live: before the
  // first response, and after any failed poll.
  degraded?: boolean;
  // spec: op-009 — the hours that may be asked for, and which one is pinned.
  // All four are optional so the screen still renders as a pure function of a
  // payload, which is what lets the panel tests drive it without a selector.
  hours?: SelectableHour[];
  // null means following the newest hour, which is the default state.
  pinnedRun?: number | null;
  onSelectHour?: (runId: number) => void;
  onFollowNewest?: () => void;
  // spec: op-010 — the evidence behind this hour's conclusions, as five named
  // states: a request in flight, one that did not arrive, the server saying no
  // pass examined this hour, a quiet hour and an explained one. Optional like
  // the four above, so the screen stays a pure function of a payload and the
  // panel tests can drive it without a fetch.
  evidence?: EvidenceView;
  // spec: op-007 — the view the control is set to, and how to change it.
  // Optional, defaulting to the view the payload was served under, so the
  // screen still renders as a pure function of a payload.
  selectedView?: ViewSelection;
  onSelectView?: (view: ViewSelection) => void;
  // spec: op-005 — how to fetch one hour unfiltered, for the drill-down tables.
  // Optional like the rest; without it View all is disabled with its reason.
  loadUnfiltered?: (runId: number) => Promise<OperationalPictureData>;
}

const OperationalPictureScreen = ({
  operationalPicture,
  degraded = false,
  hours = [],
  pinnedRun = null,
  onSelectHour,
  onFollowNewest,
  evidence = "loading",
  selectedView,
  onSelectView,
  loadUnfiltered,
}: Props) => {
  // A null summary means no detection pass has run on this run, which is not
  // the same as a pass that found nothing (api-012). The panel says so in
  // words rather than showing dashes: a reader cannot tell "—" meaning
  // *nothing to report* from "—" meaning *nobody looked*, and the second is a
  // broken pipeline. Inside a summary that is present, every value is a
  // reading — a level, never a percentage and never a decimal (FR-715, AC-11).
  const { scenario, detectionSummary, view: served } = operationalPicture;
  // What the control says, and what the rows on screen were served under. They
  // differ between a click and its answer, and the rows are named by the second
  // (op-007).
  const selected = selectedView ?? served.selected;
  // Only the conclusions. A quiet run genuinely holds about 138 track
  // discontinuities, and an analyst shown that as an anomaly count reads a
  // correct non-detection as a storm (api-012).
  const reportable = (detectionSummary?.counts ?? []).filter(
    (entry) => entry.kind === "reportable",
  );
  return (
    <main className="min-h-screen bg-[#0b0e15] text-[#e1e2ec]">
      {/* One screen high on a wide display (op-004 (4)): the header, then the
          map taking whatever height is left, with the exception panel docked
          along the bottom edge as the design reference has it. The evidence
          (op-010) sits below the fold rather than squeezing the map. */}
      <div className="flex flex-col lg:h-dvh">
        <header className="flex shrink-0 items-center justify-between border-b border-[#424754] bg-[#1d2027] px-6 py-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.05em] text-[#8c909f]">EM Fusion</p>
            <h1 className="text-xl font-semibold">{scenario?.name ?? "No scenario run"}</h1>
          </div>
          {scenario && (
            <div className="font-mono text-sm">
              <p className="text-xs uppercase tracking-[0.05em] text-[#8c909f]">Data</p>
              <p className="text-[#4cd7f6]">{dataModeLabel(scenario.dataMode)}</p>
            </div>
          )}
          {/* The hour selector (op-009). Following the newest and pinned to a
              chosen hour must be *visibly* different: pin an hour, let a batch
              land, and the screen goes on showing the pinned hour while looking
              identical to a live one — stale data in the costume of current data,
              which is the same class of defect as a health signal reporting
              healthy through an outage. So the state is stated in words and there
              is always a way back. */}
          <div className="font-mono text-sm">
            <label className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-[0.05em] text-[#8c909f]">Hour</span>
              <select
                aria-label="Hour"
                className="border border-[#424754] bg-[#0b0e15] px-2 py-1 text-[#e1e2ec]"
                disabled={hours.length === 0}
                id="operational-picture-hour"
                onChange={(event) => onSelectHour?.(Number(event.target.value))}
                value={pinnedRun === null ? "" : String(pinnedRun)}
              >
                <option value="">Newest</option>
                {hours.map((hour) => (
                  <option key={hour.runId} value={String(hour.runId)}>
                    {hourLabel(hour)}
                    {hour.examined ? "" : " · not examined"}
                  </option>
                ))}
              </select>
            </label>
            {hours.length === 0 ? (
              <p className="mt-1 text-xs text-[#8c909f]">No completed hour to choose from yet.</p>
            ) : pinnedRun === null ? (
              <p className="mt-1 text-xs text-[#8c909f]">Following the newest hour</p>
            ) : (
              <p className="mt-1 text-xs text-[#ffb786]">
                Pinned to run {pinnedRun} — not the newest.{" "}
                <button className="underline" onClick={() => onFollowNewest?.()} type="button">
                  Follow the newest
                </button>
              </p>
            )}
          </div>
          {/* The view filter (op-007). The server filters, so this decides what
              arrives at all; the line beneath it names what is ON SCREEN from
              the payload's own `view.selected`, because for a moment after a
              click the rows still belong to the previous view. A role="radio"
              button rather than an input: the option's text is its label. */}
          <div className="font-mono text-sm">
            <div aria-label="View" className="flex border border-[#424754]" role="radiogroup">
              {VIEW_OPTIONS.map((option) => (
                // biome-ignore lint/a11y/useSemanticElements: a segmented control; an <input type="radio"> carries no text of its own
                <button
                  aria-checked={option.value === selected}
                  className={
                    option.value === selected
                      ? "bg-[#adc6ff] px-2 py-1 text-xs uppercase tracking-[0.05em] text-[#0b0e15]"
                      : "px-2 py-1 text-xs uppercase tracking-[0.05em] text-[#c2c6d6] hover:text-[#e1e2ec]"
                  }
                  key={option.value}
                  onClick={() => onSelectView?.(option.value)}
                  role="radio"
                  type="button"
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p className={`mt-1 text-xs ${selected === served.selected ? "text-[#8c909f]" : "text-[#ffb786]"}`}>
              {showingSentence(served.selected, selected)}
            </p>
          </div>
          {/* `scenario.health` used to sit here as a second bare word reading
              `unknown` forever. api-014 removed the field: nothing produced it,
              and the run-level health signal it would have carried is
              `detectionSummary.signalIntegrity`, which has a producer. Service
              health is a different layer and lives in the nav footer (nav-002). */}
          <div className="text-right font-mono text-sm">
            {degraded && (
              <p className="mt-1 border border-[#df7412] px-2 py-0.5 text-xs uppercase tracking-[0.05em] text-[#ffb786]">
                Degraded — not live
              </p>
            )}
          </div>
        </header>

        <section className="grid min-h-0 flex-1 gap-4 p-6 lg:grid-cols-[1fr_360px]">
          {/* WHERE, then WHAT IS EXCEPTIONAL (op-004 (4)): the exception panel sits
              under the map and not in the rail. The receivers that used to fill
              this box are the panel's RF tab now — one list, rendered once. */}
          <div className="flex min-h-0 flex-col gap-4">
            {/* The map and the panel read the same filtered rows (map-001, op-007),
                so the two cannot disagree about what the view shows. */}
            <div className="min-h-[320px] flex-1">
              <MapView sensors={operationalPicture.rfSensors} tracks={operationalPicture.aircraftTracks} zones={operationalPicture.interferenceZones} />
            </div>
            <EmExceptionPanel
              loadUnfiltered={loadUnfiltered}
              picture={operationalPicture}
            />
          </div>

          <aside className="space-y-4 lg:overflow-y-auto">
            <section className="border border-[#424754] bg-[#1d2027] p-4">
              <h2 className="text-2xl font-semibold text-[#adc6ff]">Active Hypotheses</h2>
              {operationalPicture.hypotheses.length === 0 ? (
                <p className="mt-4 text-sm text-[#8c909f]">No active hypotheses</p>
              ) : (
                operationalPicture.hypotheses.map((hypothesis) => (
                  <article key={hypothesis.id}>
                    <h3 className="mt-4 text-xl font-semibold">{hypothesis.title}</h3>
                    {/* Both levels through the one primitive (ui-001), which
                        names these two among its four call sites. Rendered inline
                        here until this item, so a hypothesis row carrying 74.2
                        would have put a decimal on screen (FR-715, AC-11). */}
                    <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
                      <EmLevel label="Confidence" value={hypothesis.confidence} />
                      <EmLevel label="Severity" value={hypothesis.severity} />
                      <div className="col-span-2">
                        <dt className="font-mono uppercase text-[#8c909f]">Evidence</dt>
                        <dd>{hypothesis.evidence}</dd>
                      </div>
                    </dl>
                  </article>
                ))
              )}
            </section>

            <section aria-label="Detection summary" className="border border-[#424754] bg-[#1d2027] p-4">
              <h2 className="font-mono text-sm uppercase tracking-[0.05em] text-[#c2c6d6]">Detection Summary</h2>
              {detectionSummary === null ? (
                <p className="mt-4 text-sm text-[#8c909f]">
                  No detection pass has run on this run. Nothing has been examined, which is
                  not the same as nothing having been found.
                </p>
              ) : (
                <>
                  {/* Both levels through the one primitive (ui-001). Rendered
                      inline before this item, which left a backend regression
                      delivering 87 free to reach the screen: the contract types
                      these as a three-value union, and the payload is cast from
                      JSON, so the type never sees it. */}
                  <dl className="mt-4 space-y-3">
                    <EmLevel label="Anomaly Level" value={detectionSummary.anomalyLevel} />
                    <EmLevel label="Signal Integrity" value={detectionSummary.signalIntegrity} />
                  </dl>
                  <dl className="mt-4 space-y-2 border-t border-[#424754] pt-3 text-sm">
                    {reportable.map((entry) => (
                      <div key={`${entry.ruleId}:${entry.findingType}`} className="flex justify-between gap-4">
                        {/* The conclusion in words, from the module the timeline
                            below reads too (op-003, op-006). The payload carries
                            the finding type verbatim by design, and this screen
                            printed it that way until this item. */}
                        <dt className="text-[#8c909f]">{findingLabel(entry.findingType)}</dt>
                        {/* A rule that does not exist gets no number. A zero
                            there would quote the absence of a rule as the
                            accuracy of one (api-012, anom-008). */}
                        <dd className="font-mono">{entry.count ?? "—"}</dd>
                      </div>
                    ))}
                  </dl>
                </>
              )}
            </section>
          </aside>
        </section>
      </div>

      {/* The conclusion says why (op-010). Full width under the grid rather
          than in the 360px rail: a real interference account carries about
          eleven radio deviations and nine aircraft dropouts, and the rail is
          where the one-line conclusions live. The account belongs to the hour
          on screen, so pinning an hour moves it. */}
      <section className="px-6 pb-6">
        <EmEvidencePanel account={evidence} />
      </section>
    </main>
  );
};

export default OperationalPictureScreen;
