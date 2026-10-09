import { useId, useRef, useState } from "react";
import { findingLabel } from "../../lib/detectionVocabulary";
import {
  EVENTS_ARE_ANOMALOUS,
  type ExceptionTab,
  footerSentence,
  NOT_EXAMINED,
  noReceiverSentence,
  noTrackSentence,
  DRILL_DOWN_UNWIRED,
  NO_HOUR_TO_DRILL,
  QUIET_HOUR,
  tabLabel,
} from "../../lib/viewVocabulary";
import type { AircraftTrack, OperationalPicture, RFSensor, TimelineEvent } from "../../types/operationalPicture";
import { EmDrillDown } from "./EmDrillDown";
import { altitude, cell, headCell, oldestFirst, position, simulatedInstant } from "./rowFormat";

/**
 * What is exceptional in this hour, in three tabs. spec: op-004.
 *
 * The last step of the panel chain: api-016 gave an aircraft a state, api-007
 * filtered on it server-side and counted what it withheld, op-007 chose the
 * view. This panel renders the rows the view admitted and says what it hid.
 *
 * **Every word follows the view.** A tab's number is the rows it shows and its
 * word names what those rows are; the footer names the withheld rows by what
 * they are, from `view.suppressed`, because they never arrived to be counted.
 * On an hour nobody examined nothing has a state, so nothing is called nominal.
 *
 * **One list, rendered once.** The receivers used to fill the map box and the
 * timeline sat in the rail; both are here now, and nowhere else.
 *
 * **Columns are the payload's fields only.** The design reference shows a noise
 * floor, a last-signal time and a severity per receiver, and nothing produces
 * any of them.
 *
 * The open tab is component state: it survives polls, hours and views, because
 * nothing keys this component on them, and a reload opens on RF.
 *
 * **View all opens the open tab's drill-down table (op-005)** for the hour the
 * payload names, through the loader the seam hands down. It is disabled, with
 * its reason, when there is no hour to list or no loader to list it with.
 */

const TABS: readonly ExceptionTab[] = ["rf", "tracks", "events"];

const ReceiverTable = ({ sensors }: { sensors: RFSensor[] }) => (
  <table className="w-full border-collapse text-left text-sm">
    <thead>
      <tr className="border-b border-[#424754]">
        <th className={headCell}>Receiver</th>
        <th className={headCell}>Station</th>
        <th className={headCell}>Band</th>
        <th className={headCell}>State</th>
      </tr>
    </thead>
    <tbody>
      {sensors.map((sensor) => (
        <tr
          className="border-b border-[#424754]/50"
          key={sensor.id}
        >
          <td className={`${cell} font-mono`}>{sensor.id}</td>
          <td className={`${cell} text-[#4cd7f6]`}>{sensor.stationName}</td>
          <td className={`${cell} font-mono`}>{sensor.signalId}</td>
          <td className={`${cell} font-mono text-[#ffb786]`}>{sensor.health}</td>
        </tr>
      ))}
    </tbody>
  </table>
);

const TrackTable = ({ tracks }: { tracks: AircraftTrack[] }) => (
  <table className="w-full border-collapse text-left text-sm">
    <thead>
      <tr className="border-b border-[#424754]">
        <th className={headCell}>Aircraft</th>
        <th className={headCell}>Altitude</th>
        <th className={headCell}>Position</th>
        <th className={headCell}>State</th>
      </tr>
    </thead>
    <tbody>
      {tracks.map((track) => (
        <tr
          className="border-b border-[#424754]/50"
          key={track.id}
        >
          <td className={`${cell} font-mono`}>{track.name}</td>
          <td className={`${cell} font-mono`}>{altitude(track.altitudeFt)}</td>
          <td className={`${cell} font-mono`}>{position(track)}</td>
          <td className={`${cell} font-mono text-[#ffb786]`}>{track.state}</td>
        </tr>
      ))}
    </tbody>
  </table>
);

const EventList = ({ events }: { events: TimelineEvent[] }) => (
  <ol className="space-y-2 text-sm">
    {oldestFirst(events).map((timelineEvent) => (
      <li
        className="flex flex-wrap items-baseline gap-x-3 border-l-2 border-[#df7412] pl-3"
        key={timelineEvent.id}
      >
        <span className="font-mono text-xs text-[#8c909f]">{simulatedInstant(timelineEvent.time)}</span>
        <span className="text-[#e1e2ec]">{findingLabel(timelineEvent.event)}</span>
        <span className="font-mono text-xs text-[#4cd7f6]">{timelineEvent.source}</span>
      </li>
    ))}
  </ol>
);

type PanelData = Pick<OperationalPicture, "scenario" | "rfSensors" | "aircraftTracks" | "timelineEvents" | "view">;

// The hour the payload names, or null when it names none a table can be asked
// for: no run at all, or the first-paint mock's id, which is not a run.
const hourOf = (picture: PanelData): number | null =>
  picture.scenario && /^\d+$/.test(picture.scenario.id) ? Number(picture.scenario.id) : null;

export const EmExceptionPanel = ({
  picture,
  loadUnfiltered,
}: {
  picture: PanelData;
  loadUnfiltered?: (runId: number) => Promise<OperationalPicture>;
}) => {
  const [open, setOpen] = useState<ExceptionTab>("rf");
  // The table open over the screen, and the hour it was opened for: kept here,
  // so a poll that moves the screen to a newer hour leaves the table on its own.
  const [drill, setDrill] = useState<{ tab: ExceptionTab; runId: number } | null>(null);
  const viewAllRef = useRef<HTMLButtonElement>(null);
  const id = useId();
  const hour = hourOf(picture);
  const unavailable = !loadUnfiltered ? DRILL_DOWN_UNWIRED : hour === null ? NO_HOUR_TO_DRILL : null;
  const { view } = picture;
  const { selected, examined, suppressed } = view;

  const shown: Record<ExceptionTab, number> = {
    rf: picture.rfSensors.length,
    tracks: picture.aircraftTracks.length,
    events: picture.timelineEvents.length,
  };
  const hidden: Record<ExceptionTab, number> = {
    rf: suppressed.rfSensors,
    tracks: suppressed.aircraftTracks,
    events: suppressed.timelineEvents,
  };

  // What an empty tab says instead of an empty table (op-004 (3)). Three
  // different empties on Events: an hour nobody examined, a view that withheld
  // the hour's conclusions, and a quiet hour — only the last says no events.
  const emptySentence = (tab: ExceptionTab): string => {
    if (!examined) return NOT_EXAMINED;
    if (tab === "rf") return noReceiverSentence(selected);
    if (tab === "tracks") return noTrackSentence(selected);
    return hidden.events > 0 ? EVENTS_ARE_ANOMALOUS : QUIET_HOUR;
  };

  const body = (tab: ExceptionTab) => {
    if (shown[tab] === 0) return <p className="text-sm text-[#c2c6d6]">{emptySentence(tab)}</p>;
    return (
      <>
        {/* Rows can be served on an unexamined hour under All, each `unknown`. */}
        {!examined && <p className="mb-2 text-sm text-[#ffb786]">{NOT_EXAMINED}</p>}
        {tab === "rf" && <ReceiverTable sensors={picture.rfSensors} />}
        {tab === "tracks" && <TrackTable tracks={picture.aircraftTracks} />}
        {tab === "events" && <EventList events={picture.timelineEvents} />}
      </>
    );
  };

  return (
    <section
      aria-label="Exceptions"
      className="shrink-0 border border-[#424754] bg-[#1d2027]"
    >
      <div
        className="flex border-b border-[#424754]"
        role="tablist"
      >
        {TABS.map((tab) => (
          <button
            aria-controls={`${id}-${tab}-panel`}
            aria-selected={tab === open}
            className={
              tab === open
                ? "border-b-2 border-[#adc6ff] px-4 py-2 font-mono text-xs uppercase tracking-[0.05em] text-[#adc6ff]"
                : "px-4 py-2 font-mono text-xs uppercase tracking-[0.05em] text-[#c2c6d6] hover:text-[#e1e2ec]"
            }
            id={`${id}-${tab}-tab`}
            key={tab}
            onClick={() => setOpen(tab)}
            role="tab"
            type="button"
          >
            {tabLabel(tab, shown[tab], selected, examined)}
          </button>
        ))}
      </div>
      <div
        aria-labelledby={`${id}-${open}-tab`}
        id={`${id}-${open}-panel`}
        role="tabpanel"
      >
        {/* A fixed height, so switching tabs never resizes the map above. */}
        <div className="h-40 overflow-y-auto p-4">{body(open)}</div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#424754] px-4 py-2 font-mono text-xs">
          <span className="text-[#8c909f]">{footerSentence(open, hidden[open], selected, examined)}</span>
          <span className="flex items-center gap-2">
            {unavailable && <span className="text-[#8c909f]">{unavailable}</span>}
            <button
              className={
                unavailable
                  ? "uppercase tracking-[0.05em] text-[#8c909f] opacity-60"
                  : "uppercase tracking-[0.05em] text-[#adc6ff] hover:text-[#e1e2ec]"
              }
              disabled={unavailable !== null}
              onClick={() => hour !== null && setDrill({ tab: open, runId: hour })}
              ref={viewAllRef}
              type="button"
            >
              View all
            </button>
          </span>
        </div>
      </div>
      {drill && loadUnfiltered && (
        <EmDrillDown
          load={loadUnfiltered}
          onClose={() => {
            setDrill(null);
            viewAllRef.current?.focus();
          }}
          runId={drill.runId}
          tab={drill.tab}
        />
      )}
    </section>
  );
};
