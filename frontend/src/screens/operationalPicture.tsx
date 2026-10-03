import { EmLevel } from "../components/em/EmLevel";
import { findingLabel } from "../lib/detectionVocabulary";
import type {
  OperationalPicture as OperationalPictureData,
  SelectableHour,
  TimelineEvent,
} from "../types/operationalPicture";

// The instant an event happened, in the simulated time it happened at.
//
// Sliced from the ISO string rather than formatted through `Date`, deliberately
// (op-006). These are instants in a replayed 2022 hour and the run was
// generated in 2026, so a relative time states the wrong thing and a local
// format shifts the hour by the viewer's offset — anom-009's recorded mistake,
// and the same one the hour labels above had to avoid.
const simulatedInstant = (iso: string): string => `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;

// Oldest first, by event time and never by array order (op-006). api-012
// already serves them in order, so this changes nothing today — it is what
// stops the strip's order silently following the backend's.
const oldestFirst = (events: readonly TimelineEvent[]): TimelineEvent[] =>
  [...events].sort((a, b) => a.time.localeCompare(b.time));

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
}

const OperationalPictureScreen = ({
  operationalPicture,
  degraded = false,
  hours = [],
  pinnedRun = null,
  onSelectHour,
  onFollowNewest,
}: Props) => {
  // A null summary means no detection pass has run on this run, which is not
  // the same as a pass that found nothing (api-012). The panel says so in
  // words rather than showing dashes: a reader cannot tell "—" meaning
  // *nothing to report* from "—" meaning *nobody looked*, and the second is a
  // broken pipeline. Inside a summary that is present, every value is a
  // reading — a level, never a percentage and never a decimal (FR-715, AC-11).
  const { scenario, detectionSummary } = operationalPicture;
  // Only the conclusions. A quiet run genuinely holds about 138 track
  // discontinuities, and an analyst shown that as an anomaly count reads a
  // correct non-detection as a storm (api-012).
  const reportable = (detectionSummary?.counts ?? []).filter(
    (entry) => entry.kind === "reportable",
  );
  return (
    <main className="min-h-screen bg-[#0b0e15] text-[#e1e2ec]">
      <header className="flex items-center justify-between border-b border-[#424754] bg-[#1d2027] px-6 py-4">
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

      <section className="grid gap-4 p-6 lg:grid-cols-[1fr_360px]">
        <div className="min-h-[480px] border border-[#424754] bg-black p-4">
          <p className="font-mono text-xs uppercase tracking-[0.05em] text-[#8c909f]">Operational Picture</p>
          {/* Every receiver in the layout, with the state the pass found it
              in — not only the ones in trouble, which on a quiet run is an
              empty map and on a staged one is a map with no reference points
              to read the incident against (api-012, scn-005). This block
              previously labelled each one "Signal Noise", which with a single
              mock receiver was invisible and with seven claims noise on all
              of them. */}
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {operationalPicture.rfSensors.map((sensor) => (
              <div key={sensor.id} className="border border-[#424754] p-3">
                <p className="font-mono text-xs uppercase tracking-[0.05em] text-[#8c909f]">
                  {sensor.id} · {sensor.signalId}
                </p>
                <p className="mt-1 text-[#4cd7f6]">{sensor.stationName}</p>
                <p className="mt-1 font-mono text-sm text-[#ffb786]">{sensor.health}</p>
              </div>
            ))}
          </div>
        </div>

        <aside className="space-y-4">
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

          {/* The timeline strip (op-006). Carried in the payload since api-012
              and rendered nowhere until this item — and it carries the SAME
              verbatim finding type the summary above does, which is why the
              wording for both comes from one module rather than two. */}
          <section aria-label="Timeline" className="border border-[#424754] bg-[#1d2027] p-4">
            <h2 className="font-mono text-sm uppercase tracking-[0.05em] text-[#c2c6d6]">Timeline</h2>
            {operationalPicture.timelineEvents.length === 0 ? (
              <p className="mt-4 text-sm text-[#8c909f]">
                No events in this hour. Nothing the detectors reported reached the analyst.
              </p>
            ) : (
              <ol className="mt-4 space-y-2 text-sm">
                {oldestFirst(operationalPicture.timelineEvents).map((timelineEvent) => (
                  <li
                    className="flex flex-wrap items-baseline gap-x-3 border-l-2 border-[#df7412] pl-3"
                    key={timelineEvent.id}
                  >
                    <span className="font-mono text-xs text-[#8c909f]">
                      {simulatedInstant(timelineEvent.time)}
                    </span>
                    <span className="text-[#e1e2ec]">{findingLabel(timelineEvent.event)}</span>
                    <span className="font-mono text-xs text-[#4cd7f6]">{timelineEvent.source}</span>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </aside>
      </section>
    </main>
  );
};

export default OperationalPictureScreen;
