import { useId, useState } from "react";
import { findingLabel } from "../../lib/detectionVocabulary";
import {
  EVENTS_ARE_ANOMALOUS,
  type ExceptionTab,
  footerSentence,
  NOT_EXAMINED,
  noReceiverSentence,
  noTrackSentence,
  QUIET_HOUR,
  tabLabel,
  VIEW_ALL_REASON,
} from "../../lib/viewVocabulary";
import type { AircraftTrack, OperationalPicture, RFSensor, TimelineEvent } from "../../types/operationalPicture";

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
 */

const TABS: readonly ExceptionTab[] = ["rf", "tracks", "events"];

// The instant an event happened, in the simulated time it happened at (op-006):
// sliced from the ISO string, because a relative time or a local format states
// the wrong hour for a replayed 2022 hour generated in 2026.
const simulatedInstant = (iso: string): string => `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;

// Oldest first, by event time and never by array order (op-006).
const oldestFirst = (events: readonly TimelineEvent[]): TimelineEvent[] => [...events].sort((a, b) => a.time.localeCompare(b.time));

const altitude = (feet: number | null): string => (feet === null ? "not reported" : `${feet.toLocaleString("en-GB")} ft`);

const position = (track: AircraftTrack): string => `${track.lat.toFixed(2)}, ${track.lon.toFixed(2)}`;

const headCell = "px-3 py-2 font-mono text-[10px] uppercase tracking-[0.05em] text-[#8c909f]";
const cell = "px-3 py-2";

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

type PanelData = Pick<OperationalPicture, "rfSensors" | "aircraftTracks" | "timelineEvents" | "view">;

export const EmExceptionPanel = ({ picture }: { picture: PanelData }) => {
  const [open, setOpen] = useState<ExceptionTab>("rf");
  const id = useId();
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
          {/* Disabled with its reason, as RESET and REPLAY are (decided
              2026-10-06): the drill-down tables are op-005's. */}
          <span className="flex items-center gap-2">
            <span className="text-[#8c909f]">{VIEW_ALL_REASON}</span>
            <button
              className="uppercase tracking-[0.05em] text-[#8c909f] opacity-60"
              disabled
              type="button"
            >
              View all
            </button>
          </span>
        </div>
      </div>
    </section>
  );
};
